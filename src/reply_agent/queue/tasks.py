from datetime import timedelta

from rq import Queue

from reply_agent.queue.redis_client import get_redis_sync

QUEUE_NAME = "inbound_messages"

# Doc 3 roadmap (order confirmation follow-up) — "~2 hours" per the partner-meeting roadmap.
CONFIRMATION_NUDGE_DELAY = timedelta(hours=2)


def get_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=get_redis_sync())


def enqueue_inbound_message(payload: dict) -> None:
    get_queue().enqueue("reply_agent.worker.process_inbound_message", payload)


def enqueue_order_confirmation_nudge(order_id: str) -> None:
    """Scheduled, not immediate — needs scripts/run_worker.py's worker running with
    with_scheduler=True to actually promote it from RQ's ScheduledJobRegistry into the real
    queue once due (built into RQ core, no separate rq-scheduler package needed).
    """
    get_queue().enqueue_in(
        CONFIRMATION_NUDGE_DELAY, "reply_agent.worker.send_order_confirmation_nudge", order_id
    )
