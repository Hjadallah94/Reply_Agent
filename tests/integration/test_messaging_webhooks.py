"""Instagram and Messenger share the exact same webhook router shape (channels/common.py's
build_messaging_webhook_router), so one parametrized test class covers both instead of
duplicating tests/integration/test_whatsapp_webhook.py's pattern twice.
"""

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
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", VERIFY_TOKEN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _sign(body: bytes) -> str:
    digest = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _payload(object_type: str, message_id: str) -> dict:
    return {
        "object": object_type,
        "entry": [
            {
                "id": "page-123",
                "messaging": [
                    {
                        "sender": {"id": "customer-456"},
                        "recipient": {"id": "page-123"},
                        "timestamp": 1734000000,
                        "message": {"mid": message_id, "text": "hello"},
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    ("path", "object_type"),
    [("/webhooks/instagram", "instagram"), ("/webhooks/messenger", "page")],
)
class TestMessagingWebhooks:
    def test_get_verification_succeeds_with_correct_token(self, path, object_type):
        client = TestClient(app)
        response = client.get(
            path,
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "999",
            },
        )
        assert response.status_code == 200
        assert response.text == "999"

    def test_get_verification_rejects_wrong_token(self, path, object_type):
        client = TestClient(app)
        response = client.get(
            path,
            params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "999"},
        )
        assert response.status_code == 403

    def test_post_rejects_invalid_signature(self, path, object_type):
        client = TestClient(app)
        response = client.post(
            path, content=b"{}", headers={"X-Hub-Signature-256": "sha256=deadbeef"}
        )
        assert response.status_code == 403

    def test_post_enqueues_new_message(self, path, object_type):
        body = json.dumps(_payload(object_type, "mid.NEW1")).encode()
        fake_redis = AsyncMock()
        fake_redis.set.return_value = True

        with (
            patch("reply_agent.channels.common.get_redis_async", return_value=fake_redis),
            patch("reply_agent.channels.common.enqueue_inbound_message") as mock_enqueue,
        ):
            client = TestClient(app)
            response = client.post(
                path, content=body, headers={"X-Hub-Signature-256": _sign(body)}
            )

        assert response.status_code == 200
        mock_enqueue.assert_called_once()
        assert mock_enqueue.call_args[0][0]["channel_message_id"] == "mid.NEW1"

    def test_post_skips_duplicate_message(self, path, object_type):
        body = json.dumps(_payload(object_type, "mid.DUP1")).encode()
        fake_redis = AsyncMock()
        fake_redis.set.return_value = False

        with (
            patch("reply_agent.channels.common.get_redis_async", return_value=fake_redis),
            patch("reply_agent.channels.common.enqueue_inbound_message") as mock_enqueue,
        ):
            client = TestClient(app)
            response = client.post(
                path, content=body, headers={"X-Hub-Signature-256": _sign(body)}
            )

        assert response.status_code == 200
        mock_enqueue.assert_not_called()

    def test_post_ignores_events_for_a_different_object_type(self, path, object_type):
        wrong_object = "page" if object_type == "instagram" else "instagram"
        body = json.dumps(_payload(wrong_object, "mid.WRONG1")).encode()

        with patch("reply_agent.channels.common.enqueue_inbound_message") as mock_enqueue:
            client = TestClient(app)
            response = client.post(
                path, content=body, headers={"X-Hub-Signature-256": _sign(body)}
            )

        assert response.status_code == 200
        mock_enqueue.assert_not_called()
