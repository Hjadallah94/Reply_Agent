from reply_agent.channels.common import extract_messaging_events
from reply_agent.db.models import ChannelType


def _payload(messaging: list[dict]) -> dict:
    return {"object": "page", "entry": [{"id": "page-123", "messaging": messaging}]}


def test_extracts_a_text_message():
    payload = _payload(
        [
            {
                "sender": {"id": "customer-456"},
                "recipient": {"id": "page-123"},
                "timestamp": 1734000000,
                "message": {"mid": "mid.ABC", "text": "hello"},
            }
        ]
    )

    events = extract_messaging_events(payload, ChannelType.messenger)

    assert len(events) == 1
    event = events[0]
    assert event.channel == ChannelType.messenger
    assert event.business_lookup_key == "page-123"
    assert event.customer_handle == "customer-456"
    assert event.text == "hello"
    assert event.channel_message_id == "mid.ABC"


def test_skips_echoes_of_our_own_sends():
    payload = _payload(
        [
            {
                "sender": {"id": "page-123"},
                "recipient": {"id": "customer-456"},
                "timestamp": 1734000000,
                "message": {"mid": "mid.ECHO", "text": "our own reply", "is_echo": True},
            }
        ]
    )

    assert extract_messaging_events(payload, ChannelType.messenger) == []


def test_skips_non_text_messages():
    payload = _payload(
        [
            {
                "sender": {"id": "customer-456"},
                "recipient": {"id": "page-123"},
                "timestamp": 1734000000,
                "message": {"mid": "mid.IMG", "attachments": [{"type": "image"}]},
            }
        ]
    )

    assert extract_messaging_events(payload, ChannelType.instagram) == []


def test_empty_payload_returns_no_events():
    assert extract_messaging_events({"entry": []}, ChannelType.instagram) == []
