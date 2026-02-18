import json
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from redis import Redis


agent_sessions: Dict[str, Dict[str, Any]] = {}
sessions_lock = threading.Lock()
MAX_CONCURRENT_AGENTS = int(os.getenv("MAX_CONCURRENT_AGENTS", "1"))
LOG_LIMIT = 500
RUNNING_SET_KEY = "agent:sessions:running"


def _redis_client() -> Optional[Redis]:
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        return None
    return Redis.from_url(redis_url, decode_responses=True)


def _session_key(session_id: str) -> str:
    return f"agent:session:{session_id}"


def _logs_key(session_id: str) -> str:
    return f"agent:session:{session_id}:logs"


def _normalize_session(data: Dict[str, Any]) -> Dict[str, Any]:
    if not data:
        return {}
    normalized = dict(data)
    normalized["running"] = str(normalized.get("running", "false")).lower() == "true"
    normalized["stop_requested"] = str(normalized.get("stop_requested", "false")).lower() == "true"
    for nullable_key in ("current_lesson", "last_run", "job_id", "process_pid"):
        value = normalized.get(nullable_key)
        if value in ("", "None", None):
            normalized[nullable_key] = None
    return normalized


def _running_count() -> int:
    redis_client = _redis_client()
    if redis_client:
        return redis_client.scard(RUNNING_SET_KEY)
    return sum(1 for session in agent_sessions.values() if session.get("running"))


def create_session(logger, mode: str = "single") -> str:
    """Create a new session and register it as running."""
    with sessions_lock:
        if _running_count() >= MAX_CONCURRENT_AGENTS:
            raise HTTPException(
                status_code=503,
                detail=f"Maximum {MAX_CONCURRENT_AGENTS} agents running. Try again later.",
            )

        session_id = str(uuid.uuid4())[:8]
        session_data = {
            "running": True,
            "current_lesson": None,
            "mode": mode,
            "last_run": None,
            "created_at": datetime.now().isoformat(),
            "job_id": "",
            "stop_requested": False,
        }

        redis_client = _redis_client()
        if redis_client:
            redis_client.hset(_session_key(session_id), mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in session_data.items()})
            redis_client.delete(_logs_key(session_id))
            redis_client.sadd(RUNNING_SET_KEY, session_id)
        else:
            session_data["logs"] = []
            agent_sessions[session_id] = session_data

        logger.info("Session created: id=%s mode=%s", session_id, mode)
        return session_id


def get_session(session_id: str) -> Dict[str, Any]:
    if not session_id:
        return {}
    redis_client = _redis_client()
    if redis_client:
        raw = redis_client.hgetall(_session_key(session_id))
        return _normalize_session(raw)
    return agent_sessions.get(session_id, {})


def update_session(session_id: str, **fields):
    if not session_id:
        return
    redis_client = _redis_client()
    if redis_client:
        mapped = {}
        for key, value in fields.items():
            if isinstance(value, (dict, list)):
                mapped[key] = json.dumps(value)
            elif value is None:
                mapped[key] = ""
            else:
                mapped[key] = str(value)
        if mapped:
            redis_client.hset(_session_key(session_id), mapping=mapped)
        return

    session = agent_sessions.get(session_id)
    if session:
        session.update(fields)


def clear_logs(session_id: str):
    redis_client = _redis_client()
    if redis_client:
        redis_client.delete(_logs_key(session_id))
        return
    session = agent_sessions.get(session_id)
    if session is not None:
        session["logs"] = []


def append_log(session_id: str, message: str):
    redis_client = _redis_client()
    if redis_client:
        key = _logs_key(session_id)
        redis_client.rpush(key, message)
        redis_client.ltrim(key, -LOG_LIMIT, -1)
        return
    session = agent_sessions.get(session_id)
    if session is not None:
        logs = session.setdefault("logs", [])
        logs.append(message)
        if len(logs) > LOG_LIMIT:
            session["logs"] = logs[-LOG_LIMIT:]


def get_logs(session_id: str) -> List[str]:
    if not session_id:
        return []
    redis_client = _redis_client()
    if redis_client:
        return redis_client.lrange(_logs_key(session_id), 0, -1)
    session = agent_sessions.get(session_id)
    if not session:
        return []
    return session.get("logs", [])


def mark_session_finished(session_id: str):
    update_session(
        session_id,
        running=False,
        stop_requested=False,
        last_run=datetime.now().isoformat(),
    )
    redis_client = _redis_client()
    if redis_client:
        redis_client.srem(RUNNING_SET_KEY, session_id)


def set_job_id(session_id: str, job_id: str):
    update_session(session_id, job_id=job_id)


def request_stop(session_id: str):
    update_session(session_id, stop_requested=True)


def is_stop_requested(session_id: str) -> bool:
    session = get_session(session_id)
    return bool(session.get("stop_requested"))
