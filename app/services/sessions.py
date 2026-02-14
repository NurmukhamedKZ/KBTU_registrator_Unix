import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict

from fastapi import HTTPException


# Multi-session agent state: session_id -> session_data
agent_sessions: Dict[str, Dict[str, Any]] = {}
sessions_lock = threading.Lock()
MAX_CONCURRENT_AGENTS = int(os.getenv("MAX_CONCURRENT_AGENTS", "5"))


def create_session(logger, mode: str = "single") -> str:
    """Create a new session, returns session_id."""
    with sessions_lock:
        if sum(1 for s in agent_sessions.values() if s.get("running")) >= MAX_CONCURRENT_AGENTS:
            raise HTTPException(
                status_code=503,
                detail=f"Maximum {MAX_CONCURRENT_AGENTS} agents running. Try again later.",
            )
        session_id = str(uuid.uuid4())[:8]
        agent_sessions[session_id] = {
            "running": True,
            "current_lesson": None,
            "mode": mode,
            "logs": [],
            "last_run": None,
            "process": None,
            "created_at": datetime.now().isoformat(),
        }
        logger.info("Session created: id=%s mode=%s", session_id, mode)
        return session_id
