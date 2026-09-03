"""RQ worker entrypoint. The bare `rq worker` CLI reads REDIS_URL from the OS environment
(not our .env) and defaults to the fork-based Worker class, which crashes immediately on
Windows (os.fork() doesn't exist there) — this wraps both: uses our own Settings for the
Redis connection, and picks SimpleWorker (no forking, runs jobs in-process) on Windows.

with_scheduler=True (Doc 3 roadmap, order confirmation follow-up) — queue/tasks.py's
enqueue_order_confirmation_nudge uses RQ's enqueue_in, which puts a job in RQ's
ScheduledJobRegistry rather than the real queue directly; without an active scheduler (built
into RQ core since ~1.13, no separate rq-scheduler package needed) nothing ever promotes it
into the queue when it's actually due.
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
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
