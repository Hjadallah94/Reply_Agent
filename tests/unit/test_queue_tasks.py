"""queue/tasks.py — RQ enqueue helpers. Mocked Queue/get_queue throughout; no real Redis
needed for these, they only check what gets called with what.
"""

from unittest.mock import MagicMock, patch

from reply_agent.queue.tasks import CONFIRMATION_NUDGE_DELAY, enqueue_order_confirmation_nudge


def test_enqueue_order_confirmation_nudge_schedules_the_right_delay_and_target():
    mock_queue = MagicMock()
    with patch("reply_agent.queue.tasks.get_queue", return_value=mock_queue):
        enqueue_order_confirmation_nudge("order-123")

    mock_queue.enqueue_in.assert_called_once_with(
        CONFIRMATION_NUDGE_DELAY, "reply_agent.worker.send_order_confirmation_nudge", "order-123"
    )


def test_confirmation_nudge_delay_is_two_hours():
    from datetime import timedelta

    assert CONFIRMATION_NUDGE_DELAY == timedelta(hours=2)
