import os
import subprocess
import time
from datetime import datetime

from fastapi import HTTPException

from app.services.sessions import agent_sessions, sessions_lock


def run_single_agent(session_id: str, lesson_id: str, skip_video: bool, unix_email: str, unix_password: str, logger):
    """Run the agent in a background thread for a specific session."""
    session = agent_sessions.get(session_id)
    if not session:
        return

    session["running"] = True
    session["current_lesson"] = lesson_id
    session["mode"] = "single"
    session["logs"] = []
    session["process"] = None

    try:
        lesson_input = lesson_id.strip()
        if lesson_input.startswith("http://") or lesson_input.startswith("https://"):
            lesson_url = lesson_input
        else:
            lesson_url = f"https://uni-x.almv.kz/platform/lessons/{lesson_input}"

        cmd = ["python3", "unix_agent.py", "--lesson", lesson_url]
        if skip_video:
            cmd.append("--skip-video")

        logger.info(
            "Single agent started: session=%s lesson=%s skip_video=%s",
            session_id,
            lesson_id,
            skip_video,
        )

        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Starting agent for lesson {lesson_id}...")

        env = os.environ.copy()
        env["UNIX_EMAIL"] = unix_email
        env["UNIX_PASSWORD"] = unix_password

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env
        )
        session["process"] = process

        for line in iter(process.stdout.readline, ""):
            if line:
                session["logs"].append(line.strip())
                if len(session["logs"]) > 200:
                    session["logs"] = session["logs"][-200:]
            if process.poll() is not None:
                break

        process.wait()
        exit_code = process.returncode
        if exit_code in (-9, -15):
            session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ⛔ Agent stopped by user")
            logger.warning("Single agent stopped by user: session=%s", session_id)
        else:
            session["logs"].append(
                f"[{datetime.now().strftime('%H:%M:%S')}] Agent finished with exit code {exit_code}"
            )
            logger.info("Single agent finished: session=%s exit_code=%s", session_id, exit_code)

    except Exception as error:
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {str(error)}")
        logger.exception("Single agent failed: session=%s error=%s", session_id, str(error))
    finally:
        session["running"] = False
        session["process"] = None
        session["last_run"] = datetime.now().isoformat()
        logger.info("Single agent session closed: session=%s", session_id)


def run_batch_agent(session_id: str, lesson_ids: str, skip_video: bool, unix_email: str, unix_password: str, logger):
    """Run batch agent: one process, one browser, same logic as single mode in a loop."""
    import re

    session = agent_sessions.get(session_id)
    if not session:
        return

    ids = [item.strip() for item in lesson_ids.split(",") if item.strip()]
    if not ids:
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ No valid lesson IDs provided")
        session["running"] = False
        logger.warning("Batch agent rejected empty lesson ids: session=%s", session_id)
        return

    session["running"] = True
    session["current_lesson"] = f"Batch: {len(ids)} lessons ({ids[0]}...)"
    session["mode"] = "batch"
    session["logs"] = []
    session["process"] = None

    try:
        logger.info(
            "Batch agent started: session=%s count=%s skip_video=%s",
            session_id,
            len(ids),
            skip_video,
        )
        session["logs"].append(
            f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Starting BATCH mode: {len(ids)} lessons (one browser session)"
        )
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] IDs: {', '.join(ids)}")
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Skip video: {skip_video}")

        env = os.environ.copy()
        env["UNIX_EMAIL"] = unix_email
        env["UNIX_PASSWORD"] = unix_password

        cmd = ["python3", "unix_agent.py", "--lesson-ids", lesson_ids]
        if skip_video:
            cmd.append("--skip-video")

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env
        )
        session["process"] = process

        for line in iter(process.stdout.readline, ""):
            if line:
                line_stripped = line.strip()
                if "Processing lesson" in line_stripped:
                    match = re.search(r"Processing lesson (\d+).*?\((\d+)/(\d+)\)", line_stripped)
                    if match:
                        session["current_lesson"] = f"Lesson {match.group(1)} ({match.group(2)}/{match.group(3)})"
                    else:
                        fallback_match = re.search(r"Processing lesson (\d+)", line_stripped)
                        if fallback_match:
                            session["current_lesson"] = f"Lesson {fallback_match.group(1)}"

                session["logs"].append(line_stripped)
                if len(session["logs"]) > 500:
                    session["logs"] = session["logs"][-500:]
            if process.poll() is not None:
                break

        process.wait()
        exit_code = process.returncode
        session["process"] = None

        if exit_code in (-9, -15):
            session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ⛔ Batch stopped by user")
            logger.warning("Batch agent stopped by user: session=%s", session_id)
        else:
            session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 Batch complete")
            logger.info("Batch agent finished: session=%s exit_code=%s", session_id, exit_code)

    except Exception as error:
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error: {str(error)}")
        logger.exception("Batch agent failed: session=%s error=%s", session_id, str(error))
    finally:
        session["running"] = False
        session["process"] = None
        session["last_run"] = datetime.now().isoformat()
        logger.info("Batch agent session closed: session=%s", session_id)


def stop_agent_by_session(session_id: str):
    """Stop agent process for a given session."""
    with sessions_lock:
        session = agent_sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if not session.get("running"):
            return {"message": "Agent stopped"}

        process = session.get("process")
        if process:
            try:
                process.terminate()
                session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ⏹️ Stopping agent...")
                time.sleep(2)
                if process.poll() is None:
                    process.kill()
                    session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Force killed agent")
            except Exception as error:
                raise HTTPException(status_code=500, detail=str(error)) from error

        session["running"] = False
        session["process"] = None
        return {"message": "Agent stopped"}
