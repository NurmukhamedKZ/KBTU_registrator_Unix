"""RQ worker entrypoint for agent jobs (Variant A architecture)."""

import os
import sys

from rq import Worker

from app.services.queueing import get_agent_queue, get_redis_connection


def main():
    redis_conn = get_redis_connection()
    if not redis_conn:
        print("REDIS_URL is required to run worker mode.", file=sys.stderr)
        sys.exit(1)

    queue = get_agent_queue()
    queue_name = queue.name if queue else os.getenv("AGENT_QUEUE_NAME", "agent")
    worker = Worker([queue_name], connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()
