"""api/meta_compliance.py — Meta's deauthorize and data-deletion platform callbacks. Both share
onboarding/meta_signed_request.py's HMAC-SHA256 verification, so covering the happy path once
per route plus one shared tamper-detection case is enough (same reasoning as
test_messaging_webhooks.py sharing one test class for Instagram/Messenger's identical shape).
"""

import base64
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from reply_agent.api.app import app
from reply_agent.config import get_settings

APP_SECRET = "test-app-secret"


@pytest.fixture(autouse=True)
def _configure_settings(monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", APP_SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(payload: dict, secret: str = APP_SECRET) -> str:
    encoded_payload = _base64url(json.dumps(payload).encode())
    signature = hmac.new(secret.encode(), encoded_payload.encode(), hashlib.sha256).digest()
    return f"{_base64url(signature)}.{encoded_payload}"


def test_deauthorize_accepts_a_validly_signed_request():
    signed_request = _sign({"algorithm": "HMAC-SHA256", "user_id": "meta-user-1"})

    with TestClient(app) as client:
        response = client.post("/meta/deauthorize", data={"signed_request": signed_request})

    assert response.status_code == 200
    assert response.json() == {"status": "received"}


def test_data_deletion_returns_a_status_url_and_confirmation_code():
    signed_request = _sign({"algorithm": "HMAC-SHA256", "user_id": "meta-user-1"})

    with TestClient(app) as client:
        response = client.post("/meta/data-deletion", data={"signed_request": signed_request})
        assert response.status_code == 200
        body = response.json()
        assert body["confirmation_code"]
        assert body["confirmation_code"] in body["url"]

        status_page = client.get(body["url"])

    assert status_page.status_code == 200
    assert body["confirmation_code"] in status_page.text


@pytest.mark.parametrize("path", ["/meta/deauthorize", "/meta/data-deletion"])
def test_tampered_signature_is_rejected(path):
    signed_request = _sign(
        {"algorithm": "HMAC-SHA256", "user_id": "meta-user-1"}, secret="wrong-secret"
    )

    with TestClient(app) as client:
        response = client.post(path, data={"signed_request": signed_request})

    assert response.status_code == 400
