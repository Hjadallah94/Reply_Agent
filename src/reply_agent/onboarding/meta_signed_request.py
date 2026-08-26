"""Decodes and verifies Facebook's "signed_request" shape — the same HMAC-SHA256, dot-separated,
base64url payload used by both platform compliance callbacks (api/meta_compliance.py): the
deauthorize callback and the data deletion request callback. Distinct from the OAuth code
exchange in onboarding/meta_oauth.py, which is a different Meta mechanism entirely.
"""

import base64
import hashlib
import hmac
import json


class SignedRequestError(RuntimeError):
    pass


def _base64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def parse_signed_request(signed_request: str, app_secret: str) -> dict:
    try:
        encoded_signature, encoded_payload = signed_request.split(".", 1)
    except ValueError as exc:
        raise SignedRequestError("Malformed signed_request") from exc

    expected_signature = hmac.new(
        app_secret.encode(), encoded_payload.encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(_base64url_decode(encoded_signature), expected_signature):
        raise SignedRequestError("signed_request signature mismatch")

    payload = json.loads(_base64url_decode(encoded_payload))
    if payload.get("algorithm") != "HMAC-SHA256":
        raise SignedRequestError(f"Unsupported algorithm: {payload.get('algorithm')}")
    return payload
