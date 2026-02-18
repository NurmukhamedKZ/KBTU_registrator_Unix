from datetime import datetime

from fastapi import HTTPException
from rq.job import Job

from app.services.queueing import get_agent_queue, get_redis_connection
from app.services.sessions import (
    append_log,
    get_session,
    request_stop,
    set_job_id,
    update_session,
)


def enqueue_single_agent(session_id: str, lesson_id: str, skip_video: bool, unix_email: str, unix_password: str):
    queue = get_agent_queue()
    if not queue:
        raise HTTPException(status_code=503, detail="Queue not available. Set REDIS_URL for worker mode.")
    job = queue.enqueue(
        "app.workers.agent_jobs.run_single_agent_job",
        session_id,
        lesson_id,
        skip_video,
        unix_email,
        unix_password,
    )
    set_job_id(session_id, job.id)
    return job.id


def enqueue_batch_agent(session_id: str, lesson_ids: str, skip_video: bool, unix_email: str, unix_password: str):
    queue = get_agent_queue()
    if not queue:
        raise HTTPException(status_code=503, detail="Queue not available. Set REDIS_URL for worker mode.")
    job = queue.enqueue(
        "app.workers.agent_jobs.run_batch_agent_job",
        session_id,
        lesson_ids,
        skip_video,
        unix_email,
        unix_password,
    )
    set_job_id(session_id, job.id)
    return job.id


def stop_agent_by_session(session_id: str):
    """Request stop for queued/running worker job."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    request_stop(session_id)
    append_log(session_id, f"[{datetime.now().strftime('%H:%M:%S')}] ⏹️ Stop requested...")

    job_id = session.get("job_id", "")
    redis_conn = get_redis_connection()
    if job_id and redis_conn:
        try:
            job = Job.fetch(job_id, connection=redis_conn)
            if job.get_status() in {"queued", "deferred", "scheduled"}:
                job.cancel()
                update_session(session_id, running=False, last_run=datetime.now().isoformat())
                append_log(session_id, f"[{datetime.now().strftime('%H:%M:%S')}] ⛔ Job cancelled before start")
        except Exception:
            # Job may already be finished/removed; stop flag is still set for running tasks.
            pass

    return {"message": "Stop requested"}
