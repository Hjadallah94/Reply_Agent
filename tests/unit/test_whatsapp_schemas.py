from reply_agent.channels.whatsapp.schemas import extract_text_messages

SAMPLE_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "waba-id",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "962700000000",
                            "phone_number_id": "12345",
                        },
                        "contacts": [
                            {"profile": {"name": "Test Customer"}, "wa_id": "962790000000"}
                        ],
                        "messages": [
                            {
                                "from": "962790000000",
                                "id": "wamid.ABC123",
                                "timestamp": "1734000000",
                                "type": "text",
                                "text": {"body": "كم سعرها؟"},
                            },
                            {
                                "from": "962790000000",
                                "id": "wamid.DEF456",
                                "timestamp": "1734000001",
                                "type": "image",
                                "image": {"id": "media-id"},
                            },
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}


def test_extracts_only_text_messages():
    messages = extract_text_messages(SAMPLE_PAYLOAD)
    assert len(messages) == 1
    assert messages[0].channel_message_id == "wamid.ABC123"
    assert messages[0].from_wa_id == "962790000000"
    assert messages[0].phone_number_id == "12345"
    assert messages[0].text == "كم سعرها؟"


def test_empty_payload_returns_no_messages():
    assert extract_text_messages({"entry": []}) == []
