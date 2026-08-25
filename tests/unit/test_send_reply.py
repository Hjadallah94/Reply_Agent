import uuid
from unittest.mock import AsyncMock, patch

import pytest

from reply_agent.graph.nodes.send_reply import send_reply


def _state(channel: str, business_id: str | None = None) -> dict:
    return {
        "channel": channel,
        "business_id": business_id or str(uuid.uuid4()),
        "thread_id": f"{channel}:business-id:customer-handle",
        "draft_reply": {"text": "hello there"},
    }


async def test_dispatches_whatsapp_with_the_business_own_phone_number_id():
    with (
        patch(
            "reply_agent.graph.nodes.send_reply.get_whatsapp_phone_number_id",
            new=AsyncMock(return_value="business-phone-number-id"),
        ),
        patch(
            "reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()
        ) as mock_send,
    ):
        result = await send_reply(_state("whatsapp"))

    mock_send.assert_called_once_with(
        to="customer-handle", text="hello there", phone_number_id="business-phone-number-id"
    )
    assert result == {"route": "send"}


@pytest.mark.parametrize(
    ("channel", "target"),
    [
        ("instagram", "reply_agent.graph.nodes.send_reply.send_instagram_message"),
        ("messenger", "reply_agent.graph.nodes.send_reply.send_messenger_message"),
    ],
)
async def test_dispatches_with_the_business_own_page_id(channel, target):
    with (
        patch(
            "reply_agent.graph.nodes.send_reply.get_page_id",
            new=AsyncMock(return_value="business-page-id"),
        ),
        patch(target, new=AsyncMock()) as mock_send,
    ):
        result = await send_reply(_state(channel))

    mock_send.assert_called_once_with(
        to="customer-handle", text="hello there", page_id="business-page-id"
    )
    assert result == {"route": "send"}


async def test_unknown_channel_raises():
    with pytest.raises(NotImplementedError):
        await send_reply(_state("carrier_pigeon"))
