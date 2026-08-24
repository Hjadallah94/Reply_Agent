"""RQ worker entrypoint. The bare `rq worker` CLI reads REDIS_URL from the OS environment
(not our .env) and defaults to the fork-based Worker class, which crashes immediately on
Windows (os.fork() doesn't exist there) — this wraps both: uses our own Settings for the
Redis connection, and picks SimpleWorker (no forking, runs jobs in-process) on Windows.
"""

import sys

from redis import Redis
from rq import Queue
from rq.worker import SimpleWorker, Worker

from reply_agent.config import get_settings
from reply_agent.queue.tasks import QUEUE_NAME


def main() -> None:
    settings = get_settings()
    connection = Redis.from_url(settings.redis_url)
    worker_cls = SimpleWorker if sys.platform == "win32" else Worker
    worker = worker_cls([Queue(QUEUE_NAME, connection=connection)], connection=connection)
    worker.work()


if __name__ == "__main__":
    main()
