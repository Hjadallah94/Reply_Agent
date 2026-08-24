from unittest.mock import AsyncMock, patch

import pytest

from reply_agent.graph.nodes.send_reply import send_reply


def _state(channel: str) -> dict:
    return {
        "channel": channel,
        "thread_id": f"{channel}:business-id:customer-handle",
        "draft_reply": {"text": "hello there"},
    }


@pytest.mark.parametrize(
    ("channel", "target"),
    [
        ("whatsapp", "reply_agent.graph.nodes.send_reply.send_whatsapp_message"),
        ("instagram", "reply_agent.graph.nodes.send_reply.send_instagram_message"),
        ("messenger", "reply_agent.graph.nodes.send_reply.send_messenger_message"),
    ],
)
async def test_dispatches_to_the_right_channel_client(channel, target):
    with patch(target, new=AsyncMock()) as mock_send:
        result = await send_reply(_state(channel))

    mock_send.assert_called_once_with(to="customer-handle", text="hello there")
    assert result == {"route": "send"}


async def test_unknown_channel_raises():
    with pytest.raises(NotImplementedError):
        await send_reply(_state("carrier_pigeon"))
