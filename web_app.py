"""
FastAPI Web Interface for UniX Agent

Provides a web UI to:
- View stored questions and answers
- Start the agent to process lessons
- Monitor agent status
- Supports multiple concurrent users (multi-session)
"""

import csv
import io
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db_models import DatabaseManager

load_dotenv()

app = FastAPI(title="Uni-Bot Backend", version="3.0.0")

# Multi-session agent state: session_id -> session_data
agent_sessions: Dict[str, Dict[str, Any]] = {}
sessions_lock = threading.Lock()
MAX_CONCURRENT_AGENTS = int(os.getenv("MAX_CONCURRENT_AGENTS", "5"))


def _create_session(mode: str = "single") -> str:
    """Create a new session, returns session_id."""
    with sessions_lock:
        if sum(1 for s in agent_sessions.values() if s.get("running")) >= MAX_CONCURRENT_AGENTS:
            raise HTTPException(
                status_code=503,
                detail=f"Maximum {MAX_CONCURRENT_AGENTS} agents running. Try again later."
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
        return session_id



# Database manager
db_manager = None

def get_db():
    global db_manager
    if db_manager is None:
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            db_manager = DatabaseManager(database_url)
    return db_manager


class LessonRequest(BaseModel):
    lesson_id: str
    skip_video: bool = True
    unix_email: str = ""
    unix_password: str = ""


class BatchRequest(BaseModel):
    """Comma-separated lesson IDs, e.g. '9843, 9845, 9910'"""
    lesson_ids: str
    skip_video: bool = False
    unix_email: str = ""
    unix_password: str = ""


class StopRequest(BaseModel):
    session_id: str = ""


class AgentStatus(BaseModel):
    running: bool
    current_lesson: Optional[str]
    last_run: Optional[str]
    log_count: int
    session_id: Optional[str] = None


def _run_agent_impl(session_id: str, lesson_id: str, skip_video: bool, unix_email: str, unix_password: str):
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
        # Accept both full URL and lesson ID
        lesson_input = lesson_id.strip()
        if lesson_input.startswith("http://") or lesson_input.startswith("https://"):
            lesson_url = lesson_input
        else:
            lesson_url = f"https://uni-x.almv.kz/platform/lessons/{lesson_input}"
        cmd = ["python3", "unix_agent.py", "--lesson", lesson_url]
        if skip_video:
            cmd.append("--skip-video")
        
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Starting agent for lesson {lesson_id}...")
        
        env = os.environ.copy()
        env["UNIX_EMAIL"] = unix_email
        env["UNIX_PASSWORD"] = unix_password
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        session["process"] = process
        
        for line in iter(process.stdout.readline, ''):
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
        else:
            session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Agent finished with exit code {exit_code}")
        
    except Exception as e:
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {str(e)}")
    finally:
        session["running"] = False
        session["process"] = None
        session["last_run"] = datetime.now().isoformat()


def _run_batch_agent_impl(session_id: str, lesson_ids: str, skip_video: bool, unix_email: str, unix_password: str):
    """Run batch agent: one process, one browser, same logic as single mode in a loop."""
    import re
    session = agent_sessions.get(session_id)
    if not session:
        return
    
    ids = [x.strip() for x in lesson_ids.split(",") if x.strip()]
    if not ids:
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ No valid lesson IDs provided")
        session["running"] = False
        return
    
    session["running"] = True
    session["current_lesson"] = f"Batch: {len(ids)} lessons ({ids[0]}...)"
    session["mode"] = "batch"
    session["logs"] = []
    session["process"] = None
    
    try:
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Starting BATCH mode: {len(ids)} lessons (one browser session)")
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] IDs: {', '.join(ids)}")
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Skip video: {skip_video}")
        
        env = os.environ.copy()
        env["UNIX_EMAIL"] = unix_email
        env["UNIX_PASSWORD"] = unix_password
        
        cmd = ["python3", "unix_agent.py", "--lesson-ids", lesson_ids]
        if skip_video:
            cmd.append("--skip-video")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        session["process"] = process
        
        for line in iter(process.stdout.readline, ''):
            if line:
                line_stripped = line.strip()
                if "Processing lesson" in line_stripped:
                    match = re.search(r'Processing lesson (\d+).*?\((\d+)/(\d+)\)', line_stripped)
                    if match:
                        session["current_lesson"] = f"Lesson {match.group(1)} ({match.group(2)}/{match.group(3)})"
                    else:
                        m = re.search(r'Processing lesson (\d+)', line_stripped)
                        if m:
                            session["current_lesson"] = f"Lesson {m.group(1)}"
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
        else:
            session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 Batch complete")
        
    except Exception as e:
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error: {str(e)}")
    finally:
        session["running"] = False
        session["process"] = None
        session["last_run"] = datetime.now().isoformat()


FRONTEND_DIST_DIR = Path(__file__).parent / "frontend" / "dist"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"

if FRONTEND_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS_DIR), name="frontend-assets")


def _frontend_index_path() -> Path:
    return FRONTEND_DIST_DIR / "index.html"


def _serve_frontend_index() -> FileResponse:
    """Serve SPA entrypoint with no-cache headers to avoid stale asset hashes."""
    return FileResponse(
        _frontend_index_path(),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/")
async def home():
    """Serve React frontend."""
    index_path = _frontend_index_path()
    if not index_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend build not found. Run: cd frontend && npm install && npm run build",
        )
    return _serve_frontend_index()


@app.post("/api/agent/start")
async def start_agent(request: LessonRequest):
    """Start the agent - creates new session for this user."""
    if not request.unix_email or not request.unix_password:
        raise HTTPException(status_code=400, detail="UniX email and password are required")
    
    session_id = _create_session(mode="single")
    
    thread = threading.Thread(
        target=_run_agent_impl,
        args=(session_id, request.lesson_id, request.skip_video, request.unix_email, request.unix_password)
    )
    thread.daemon = True
    thread.start()
    
    return {"message": "Agent started", "lesson_id": request.lesson_id, "session_id": session_id}


@app.post("/api/agent/batch")
async def start_batch_agent(request: BatchRequest):
    """Start batch agent - processes comma-separated lesson IDs sequentially."""
    if not request.unix_email or not request.unix_password:
        raise HTTPException(status_code=400, detail="UniX email and password are required")
    if not request.lesson_ids or not any(x.strip() for x in request.lesson_ids.split(",")):
        raise HTTPException(status_code=400, detail="At least one lesson ID is required (comma-separated)")
    
    session_id = _create_session(mode="batch")
    
    thread = threading.Thread(
        target=_run_batch_agent_impl,
        args=(session_id, request.lesson_ids, request.skip_video, request.unix_email, request.unix_password)
    )
    thread.daemon = True
    thread.start()
    
    ids = [x.strip() for x in request.lesson_ids.split(",") if x.strip()]
    return {
        "message": "Batch agent started",
        "session_id": session_id,
        "lesson_ids": ids,
        "count": len(ids)
    }


@app.post("/api/agent/stop")
async def stop_agent(request: StopRequest):
    """Stop the agent for this session."""
    session_id = request.session_id
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    
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
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        session["running"] = False
        session["process"] = None
    
    return {"message": "Agent stopped"}


@app.get("/api/agent/status")
async def get_agent_status(session_id: str = Query("", alias="session_id")) -> AgentStatus:
    """Get agent status for a session."""
    if not session_id:
        return AgentStatus(running=False, current_lesson=None, last_run=None, log_count=0, session_id=None)
    
    session = agent_sessions.get(session_id)
    if not session:
        return AgentStatus(running=False, current_lesson=None, last_run=None, log_count=0, session_id=session_id)
    
    return AgentStatus(
        running=session.get("running", False),
        current_lesson=session.get("current_lesson"),
        last_run=session.get("last_run"),
        log_count=len(session.get("logs", [])),
        session_id=session_id
    )


@app.get("/api/agent/logs")
async def get_agent_logs(session_id: str = Query("", alias="session_id")) -> List[str]:
    """Get agent logs for a session."""
    if not session_id:
        return []
    session = agent_sessions.get(session_id)
    if not session:
        return []
    return session.get("logs", [])


@app.get("/api/questions")
async def get_questions(limit: int = 20, offset: int = 0):
    """Get saved questions with pagination. Shows all questions (shared demo - no user filter)."""
    db = get_db()
    if not db:
        return {"questions": [], "total": 0}
    
    questions = db.get_all_questions(limit=limit, offset=offset)
    total = db.get_all_question_count()
    
    return {"questions": questions, "total": total}


@app.get("/api/questions/count")
async def get_question_count():
    """Get total number of questions."""
    db = get_db()
    if not db:
        return {"count": 0}
    
    count = db.get_all_question_count()
    return {"count": count}


@app.get("/api/questions/export/csv")
async def export_questions_csv():
    """Export all questions to CSV (as stored in DB)."""
    db = get_db()
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")
    
    questions = db.get_all_questions(limit=None, offset=0)
    
    # Find max answers count
    max_answers = max((len(q.get("answers", [])) for q in questions), default=0)
    
    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        # Header: id, question_text, lesson_name, lesson_url, created_at, user_email, answer_1..N, selected_answer
        header = ["id", "question_text", "lesson_name", "lesson_url", "created_at", "user_email"]
        header += [f"answer_{i+1}" for i in range(max_answers)]
        header.append("selected_answer")
        writer.writerow(header)
        
        for q in questions:
            answers = q.get("answers", [])
            selected = next((a["text"] for a in answers if a.get("is_selected")), "")
            row = [
                q.get("id"),
                q.get("question_text", ""),
                q.get("lesson_name", ""),
                q.get("lesson_url", ""),
                q.get("created_at", ""),
                q.get("user_email", ""),
            ]
            for i in range(max_answers):
                row.append(answers[i]["text"] if i < len(answers) else "")
            row.append(selected)
            writer.writerow(row)
        
        buffer.seek(0)
        return buffer.getvalue()
    
    # Add BOM for Excel UTF-8
    content = "\ufeff" + generate()
    
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=questions.csv"}
    )


@app.get("/{full_path:path}")
async def frontend_routes(full_path: str):
    """Serve React routes and static files that are outside /assets."""
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    index_path = _frontend_index_path()
    if not index_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend build not found. Run: cd frontend && npm install && npm run build",
        )

    requested_file = (FRONTEND_DIST_DIR / full_path).resolve()
    frontend_dist_resolved = FRONTEND_DIST_DIR.resolve()

    if frontend_dist_resolved not in requested_file.parents and requested_file != frontend_dist_resolved:
        raise HTTPException(status_code=404, detail="Not found")

    if requested_file.exists() and requested_file.is_file():
        return FileResponse(requested_file)

    # For missing static files (js/css/png/etc.) return 404 instead of index.html.
    # Otherwise browser can receive HTML as JS and render a blank screen.
    if Path(full_path).suffix:
        raise HTTPException(status_code=404, detail=f"Static file not found: {full_path}")

    return _serve_frontend_index()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
