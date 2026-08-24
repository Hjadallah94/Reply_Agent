"""WhatsApp Cloud API webhook payload shape. This shape has been stable for a long time, but
re-verify against Meta's current webhook reference before go-live — only text messages are
handled in Phase 1 (Doc 3 Phase 1 scope); other message types (image, audio, location, ...)
are silently skipped for now, a natural Phase 2+ extension point.
"""

from reply_agent.channels.common import NormalizedInboundEvent
from reply_agent.db.models import ChannelType


def extract_text_messages(payload: dict) -> list[NormalizedInboundEvent]:
    events: list[NormalizedInboundEvent] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id", "")
            for message in value.get("messages", []):
                if message.get("type") != "text":
                    continue
                events.append(
                    NormalizedInboundEvent(
                        channel=ChannelType.whatsapp,
                        business_lookup_key=phone_number_id,
                        customer_handle=message["from"],
                        text=message["text"]["body"],
                        channel_message_id=message["id"],
                        received_at=message["timestamp"],
                    )
                )
    return events
