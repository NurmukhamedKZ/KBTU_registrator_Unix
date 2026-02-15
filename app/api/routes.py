import threading
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse

from app.models.schemas import AgentStatus, BatchRequest, LessonRequest, StopRequest
from app.deps.database import get_db
from app.services.agent_runner import run_batch_agent, run_single_agent, stop_agent_by_session
from app.services.questions import build_questions_csv
from app.services.sessions import agent_sessions, create_session
from app.services.frontend import (
    FRONTEND_DIST_DIR,
    build_frontend_redirect_target,
    ensure_frontend_built_or_503,
    serve_frontend_index,
)


router = APIRouter()


def register_routes(logger):
    @router.post("/api/agent/start")
    async def start_agent(request: LessonRequest):
        """Start the agent - creates new session for this user."""
        if not request.unix_email or not request.unix_password:
            raise HTTPException(status_code=400, detail="UniX email and password are required")

        logger.info("API start single requested: lesson=%s", request.lesson_id)
        session_id = create_session(logger=logger, mode="single")

        thread = threading.Thread(
            target=run_single_agent,
            args=(
                session_id,
                request.lesson_id,
                request.skip_video,
                request.unix_email,
                request.unix_password,
                logger,
            ),
        )
        thread.daemon = True
        thread.start()
        return {"message": "Agent started", "lesson_id": request.lesson_id, "session_id": session_id}

    @router.post("/api/agent/batch")
    async def start_batch_agent(request: BatchRequest):
        """Start batch agent - processes comma-separated lesson IDs sequentially."""
        if not request.unix_email or not request.unix_password:
            raise HTTPException(status_code=400, detail="UniX email and password are required")
        if not request.lesson_ids or not any(item.strip() for item in request.lesson_ids.split(",")):
            raise HTTPException(status_code=400, detail="At least one lesson ID is required (comma-separated)")

        logger.info("API start batch requested: lesson_ids=%s", request.lesson_ids)
        session_id = create_session(logger=logger, mode="batch")

        thread = threading.Thread(
            target=run_batch_agent,
            args=(
                session_id,
                request.lesson_ids,
                request.skip_video,
                request.unix_email,
                request.unix_password,
                logger,
            ),
        )
        thread.daemon = True
        thread.start()

        ids = [item.strip() for item in request.lesson_ids.split(",") if item.strip()]
        return {
            "message": "Batch agent started",
            "session_id": session_id,
            "lesson_ids": ids,
            "count": len(ids),
        }

    @router.post("/api/agent/stop")
    async def stop_agent(request: StopRequest):
        """Stop the agent for this session."""
        session_id = request.session_id
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id required")

        logger.info("API stop requested: session=%s", session_id)
        return stop_agent_by_session(session_id)

    @router.get("/api/agent/status")
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
            session_id=session_id,
        )

    @router.get("/api/agent/logs")
    async def get_agent_logs(session_id: str = Query("", alias="session_id")) -> List[str]:
        """Get agent logs for a session."""
        if not session_id:
            return []
        session = agent_sessions.get(session_id)
        if not session:
            return []
        return session.get("logs", [])

    @router.get("/api/questions")
    async def get_questions(limit: int = 20, offset: int = 0):
        """Get saved questions with pagination. Shows all questions (shared demo - no user filter)."""
        db = get_db()
        if not db:
            return {"questions": [], "total": 0}
        
        # logger.info("API get questions requested: limit=%s offset=%s", limit, offset)

        questions = db.get_all_questions(limit=limit, offset=offset)
        total = db.get_all_question_count()

        logger.info("API get questions response: questions_count=%s total_count=%s", len(questions), total)
        return {"questions": questions, "total": total}

    @router.get("/api/questions/count")
    async def get_question_count():
        """Get total number of questions."""
        db = get_db()
        if not db:
            return {"count": 0}

        count = db.get_all_question_count()
        return {"count": count}

    @router.get("/api/questions/export/csv")
    async def export_questions_csv():
        """Export all questions to CSV (as stored in DB)."""
        db = get_db()
        if not db:
            raise HTTPException(status_code=503, detail="Database not available")

        questions = db.get_all_questions(limit=None, offset=0)
        content = build_questions_csv(questions)

        logger.info("API export questions csv response: questions_count=%s", len(questions))

        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=questions.csv"},
        )

    @router.get("/")
    async def home():
        """Serve React frontend."""
        redirect_target = build_frontend_redirect_target()
        if redirect_target:
            return RedirectResponse(url=redirect_target, status_code=307)
        ensure_frontend_built_or_503()
        return serve_frontend_index()

    @router.get("/{full_path:path}")
    async def frontend_routes(full_path: str, request: Request):
        """Serve React routes and static files that are outside /assets."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        redirect_target = build_frontend_redirect_target(full_path, dict(request.query_params))
        if redirect_target:
            return RedirectResponse(url=redirect_target, status_code=307)

        ensure_frontend_built_or_503()

        requested_file = (FRONTEND_DIST_DIR / full_path).resolve()
        frontend_dist_resolved = FRONTEND_DIST_DIR.resolve()

        if frontend_dist_resolved not in requested_file.parents and requested_file != frontend_dist_resolved:
            raise HTTPException(status_code=404, detail="Not found")

        if requested_file.exists() and requested_file.is_file():
            return FileResponse(requested_file)

        if Path(full_path).suffix:
            raise HTTPException(status_code=404, detail=f"Static file not found: {full_path}")

        return serve_frontend_index()

    return router
