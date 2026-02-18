import os
from dotenv import load_dotenv
from typing import Optional

from redis import Redis
from rq import Queue

load_dotenv()

def get_redis_connection() -> Optional[Redis]:
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        return None
    return Redis.from_url(redis_url, decode_responses=True)


def get_agent_queue() -> Optional[Queue]:
    redis_conn = get_redis_connection()
    if not redis_conn:
        return None
    queue_name = os.getenv("AGENT_QUEUE_NAME", "agent")
    return Queue(queue_name, connection=redis_conn, default_timeout=60 * 60 * 6)
