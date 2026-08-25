"""worker.py's event loop handling. Real DB (no mocking needed — a business_lookup_key that
matches nothing is enough to exercise this without the expense of running the full graph).
"""

from reply_agent.worker import process_inbound_message


def _payload(channel_message_id: str) -> dict:
    return {
        "channel": "whatsapp",
        "business_lookup_key": "no-such-phone-number-id",
        "customer_handle": "962790009999",
        "text": "hello",
        "channel_message_id": channel_message_id,
        "received_at": "2026-08-25T12:00:00Z",
    }


def test_process_inbound_message_survives_being_called_twice_in_a_row():
    """Regression test: scripts/run_worker.py's SimpleWorker calls this synchronously, once per
    job, in the same process for its whole lifetime. It used to wrap each call in its own
    asyncio.run(), which creates and closes a fresh event loop every time — but db/session.py's
    get_engine() and db/tenant_session.py's get_app_engine() are @lru_cache'd for the process's
    whole life, so their connection pools stayed bound to whichever loop was active the first
    time they were used. The second call in a worker's life used to crash outright ("Event loop
    is closed") the moment it touched the DB. No business matches business_lookup_key here, so
    this returns early — enough to exercise the connection-reuse path without the cost of
    running the full graph pipeline.
    """
    process_inbound_message(_payload("wamid-worker-loop-test-1"))
    process_inbound_message(_payload("wamid-worker-loop-test-2"))
