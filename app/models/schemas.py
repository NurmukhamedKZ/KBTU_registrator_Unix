from typing import Optional

from pydantic import BaseModel


class LessonRequest(BaseModel):
    lesson_id: str
    skip_video: bool = True
    unix_email: str = ""
    unix_password: str = ""


class BatchRequest(BaseModel):
    """Comma-separated lesson IDs, e.g. '9843, 9845, 9910'."""

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
