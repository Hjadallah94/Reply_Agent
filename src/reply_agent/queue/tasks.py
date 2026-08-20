from rq import Queue

from reply_agent.queue.redis_client import get_redis_sync

QUEUE_NAME = "inbound_messages"


def get_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=get_redis_sync())


def enqueue_inbound_message(payload: dict) -> None:
    get_queue().enqueue("reply_agent.worker.process_inbound_message", payload)
