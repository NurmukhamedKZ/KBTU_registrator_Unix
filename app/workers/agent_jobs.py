import os
import re
import subprocess
from datetime import datetime

from app.services.sessions import (
    append_log,
    clear_logs,
    is_stop_requested,
    mark_session_finished,
    update_session,
)


def _timestamp_message(message: str) -> str:
    return f"[{datetime.now().strftime('%H:%M:%S')}] {message}"


def _base_env(unix_email: str, unix_password: str):
    env = os.environ.copy()
    env["UNIX_EMAIL"] = unix_email
    env["UNIX_PASSWORD"] = unix_password
    return env


def run_single_agent_job(session_id: str, lesson_id: str, skip_video: bool, unix_email: str, unix_password: str):
    """Queue job: run single lesson agent and stream logs into session store."""
    lesson_input = lesson_id.strip()
    if lesson_input.startswith("http://") or lesson_input.startswith("https://"):
        lesson_url = lesson_input
    else:
        lesson_url = f"https://uni-x.almv.kz/platform/lessons/{lesson_input}"

    clear_logs(session_id)
    update_session(
        session_id,
        running=True,
        mode="single",
        current_lesson=lesson_id,
    )
    append_log(session_id, _timestamp_message(f"Starting agent for lesson {lesson_id}..."))

    cmd = ["python3", "unix_agent.py", "--lesson", lesson_url]
    if skip_video:
        cmd.append("--skip-video")

    process = None
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=_base_env(unix_email, unix_password),
        )
        update_session(session_id, process_pid=process.pid)

        for line in iter(process.stdout.readline, ""):
            if is_stop_requested(session_id):
                append_log(session_id, _timestamp_message("⏹️ Stopping agent..."))
                process.terminate()
                break
            if line:
                append_log(session_id, line.strip())
            if process.poll() is not None:
                break

        process.wait()
        exit_code = process.returncode
        if exit_code in (-9, -15):
            append_log(session_id, _timestamp_message("⛔ Agent stopped by user"))
        else:
            append_log(session_id, _timestamp_message(f"Agent finished with exit code {exit_code}"))
    except Exception as error:
        append_log(session_id, _timestamp_message(f"Error: {str(error)}"))
    finally:
        mark_session_finished(session_id)
        update_session(session_id, process_pid="", current_lesson="")
        if process and process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass


def run_batch_agent_job(session_id: str, lesson_ids: str, skip_video: bool, unix_email: str, unix_password: str):
    """Queue job: run batch lessons in one browser session and stream logs."""
    ids = [item.strip() for item in lesson_ids.split(",") if item.strip()]
    if not ids:
        append_log(session_id, _timestamp_message("❌ No valid lesson IDs provided"))
        mark_session_finished(session_id)
        return

    clear_logs(session_id)
    update_session(
        session_id,
        running=True,
        mode="batch",
        current_lesson=f"Batch: {len(ids)} lessons ({ids[0]}...)",
    )

    append_log(session_id, _timestamp_message(f"🚀 Starting BATCH mode: {len(ids)} lessons (one browser session)"))
    append_log(session_id, _timestamp_message(f"IDs: {', '.join(ids)}"))
    append_log(session_id, _timestamp_message(f"Skip video: {skip_video}"))

    cmd = ["python3", "unix_agent.py", "--lesson-ids", lesson_ids]
    if skip_video:
        cmd.append("--skip-video")

    process = None
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=_base_env(unix_email, unix_password),
        )
        update_session(session_id, process_pid=process.pid)

        for line in iter(process.stdout.readline, ""):
            if is_stop_requested(session_id):
                append_log(session_id, _timestamp_message("⏹️ Stopping batch..."))
                process.terminate()
                break
            if line:
                stripped = line.strip()
                if "Processing lesson" in stripped:
                    match = re.search(r"Processing lesson (\d+).*?\((\d+)/(\d+)\)", stripped)
                    if match:
                        update_session(
                            session_id,
                            current_lesson=f"Lesson {match.group(1)} ({match.group(2)}/{match.group(3)})",
                        )
                    else:
                        fallback_match = re.search(r"Processing lesson (\d+)", stripped)
                        if fallback_match:
                            update_session(session_id, current_lesson=f"Lesson {fallback_match.group(1)}")
                append_log(session_id, stripped)
            if process.poll() is not None:
                break

        process.wait()
        exit_code = process.returncode
        if exit_code in (-9, -15):
            append_log(session_id, _timestamp_message("⛔ Batch stopped by user"))
        else:
            append_log(session_id, _timestamp_message("🏁 Batch complete"))
    except Exception as error:
        append_log(session_id, _timestamp_message(f"❌ Error: {str(error)}"))
    finally:
        mark_session_finished(session_id)
        update_session(session_id, process_pid="", current_lesson="")
        if process and process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass
