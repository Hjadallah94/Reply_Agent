import uuid
from unittest.mock import AsyncMock, patch

import pytest

from reply_agent.graph.nodes.send_reply import send_reply


def _state(channel: str, business_id: str = "00000000-0000-0000-0000-000000000001") -> dict:
    return {
        "channel": channel,
        "business_id": business_id,
        "thread_id": f"{channel}:business-id:customer-handle",
        "draft_reply": {"text": "hello there"},
    }


@pytest.mark.parametrize(
    ("channel", "target"),
    [
        ("instagram", "reply_agent.graph.nodes.send_reply.send_instagram_message"),
        ("messenger", "reply_agent.graph.nodes.send_reply.send_messenger_message"),
    ],
)
async def test_dispatches_to_the_right_channel_client(channel, target):
    with patch(target, new=AsyncMock()) as mock_send:
        result = await send_reply(_state(channel))

    mock_send.assert_called_once_with(to="customer-handle", text="hello there")
    assert result == {"route": "send"}


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
        result = await send_reply(_state("whatsapp", business_id=str(uuid.uuid4())))

    mock_send.assert_called_once_with(
        to="customer-handle", text="hello there", phone_number_id="business-phone-number-id"
    )
    assert result == {"route": "send"}


async def test_unknown_channel_raises():
    with pytest.raises(NotImplementedError):
        await send_reply(_state("carrier_pigeon"))
