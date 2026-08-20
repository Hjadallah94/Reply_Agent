import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from reply_agent.api.app import app
from reply_agent.config import get_settings

APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"


@pytest.fixture(autouse=True)
def _configure_settings(monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", APP_SECRET)
    monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", VERIFY_TOKEN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _sign(body: bytes) -> str:
    digest = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_get_verification_succeeds_with_correct_token():
    client = TestClient(app)
    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 200
    assert response.text == "12345"


def test_get_verification_rejects_wrong_token():
    client = TestClient(app)
    response = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"},
    )
    assert response.status_code == 403


def test_post_rejects_invalid_signature():
    client = TestClient(app)
    response = client.post(
        "/webhooks/whatsapp", content=b"{}", headers={"X-Hub-Signature-256": "sha256=deadbeef"}
    )
    assert response.status_code == 403


def test_post_enqueues_new_text_message():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "12345"},
                            "messages": [
                                {
                                    "from": "962790000000",
                                    "id": "wamid.NEW1",
                                    "timestamp": "1734000000",
                                    "type": "text",
                                    "text": {"body": "hello"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()

    fake_redis = AsyncMock()
    fake_redis.set.return_value = True  # SETNX succeeded -> new message

    with (
        patch("reply_agent.channels.whatsapp.webhook.get_redis_async", return_value=fake_redis),
        patch("reply_agent.channels.whatsapp.webhook.enqueue_inbound_message") as mock_enqueue,
    ):
        client = TestClient(app)
        response = client.post(
            "/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": _sign(body)}
        )

    assert response.status_code == 200
    mock_enqueue.assert_called_once()
    assert mock_enqueue.call_args[0][0]["channel_message_id"] == "wamid.NEW1"


def test_post_skips_duplicate_message():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "12345"},
                            "messages": [
                                {
                                    "from": "962790000000",
                                    "id": "wamid.DUP1",
                                    "timestamp": "1734000000",
                                    "type": "text",
                                    "text": {"body": "hello again"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()

    fake_redis = AsyncMock()
    fake_redis.set.return_value = False  # SETNX found an existing key -> duplicate

    with (
        patch("reply_agent.channels.whatsapp.webhook.get_redis_async", return_value=fake_redis),
        patch("reply_agent.channels.whatsapp.webhook.enqueue_inbound_message") as mock_enqueue,
    ):
        client = TestClient(app)
        response = client.post(
            "/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": _sign(body)}
        )

    assert response.status_code == 200
    mock_enqueue.assert_not_called()
