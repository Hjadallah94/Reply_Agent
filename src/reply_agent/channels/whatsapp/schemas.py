"""WhatsApp Cloud API webhook payload shapes. This shape has been stable for a long time, but
re-verify against Meta's current webhook reference before go-live — only text messages are
handled in Phase 1 (Doc 3 Phase 1 scope); other message types (image, audio, location, ...)
are silently skipped for now, a natural Phase 2 extension point.
"""

from pydantic import BaseModel


class NormalizedInboundMessage(BaseModel):
    phone_number_id: str
    from_wa_id: str
    channel_message_id: str
    text: str
    timestamp: str


def extract_text_messages(payload: dict) -> list[NormalizedInboundMessage]:
    results: list[NormalizedInboundMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id", "")
            for message in value.get("messages", []):
                if message.get("type") != "text":
                    continue
                results.append(
                    NormalizedInboundMessage(
                        phone_number_id=phone_number_id,
                        from_wa_id=message["from"],
                        channel_message_id=message["id"],
                        text=message["text"]["body"],
                        timestamp=message["timestamp"],
                    )
                )
    return results
