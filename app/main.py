"""
FastAPI Web Interface for UniX Agent.

Provides a web UI to:
- View stored questions and answers
- Start the agent to process lessons
- Monitor agent status
- Supports multiple concurrent users (multi-session)
"""

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.api.routes import register_routes
from app.core.logging import setup_backend_logging
from app.services.frontend import mount_frontend_assets


load_dotenv()

app = FastAPI(title="Uni-Bot Backend", version="3.0.0")
logger = setup_backend_logging()

raw_frontend_urls = os.getenv("FRONTEND_URL", "")
allowed_origins = [item.strip() for item in raw_frontend_urls.split(",") if item.strip()]

if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS enabled for origins: %s", ", ".join(allowed_origins))

mount_frontend_assets(app)
app.include_router(register_routes(logger))
