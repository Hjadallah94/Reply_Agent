"""Same as demo_webhook_trigger.py, but targets the staging web service directly rather than
localhost — for live-verifying staging (Phase 6c and beyond) without ever touching Meta's real
webhook callback config, which must stay pointed at production throughout Meta App Review.
Never routes through Meta's real API at all: this POSTs a correctly-signed, Meta-shaped payload
straight at our own /webhooks/whatsapp endpoint, so no real phone or real Meta traffic involved.

Defaults to Amman Cookie Co's phone_number_id ("demo-cookie-shop-001", seeded specifically for
this purpose — see scripts/seed_business.py) so it routes to the real cookie catalog/address/
delivery_rules, not a business needing a temporary workaround.

Usage: uv run python scripts/demo_webhook_trigger_staging.py "1 box of 6 Chocolate Chip"
       uv run python scripts/demo_webhook_trigger_staging.py "..." 962790005555  # pick a fresh
       thread by using a different fake customer number — avoids stacking multiple unresolved
       order messages onto the same conversation, which confuses generate_response about which
       message it's actually replying to (a real, separate finding, not a Phase 6c bug).
"""

import hashlib
import hmac
import json
import sys
import time
import uuid

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import httpx

from reply_agent.config import get_settings

STAGING_WEBHOOK_URL = "https://reply-agent-web-staging.onrender.com/webhooks/whatsapp"
DEMO_PHONE_NUMBER_ID = "demo-cookie-shop-001"
DEFAULT_CUSTOMER_NUMBER = "962790006666"  # fake — never a real recipient, never actually sends


def build_payload(text: str, phone_number_id: str, customer_number: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "demo-waba-id",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "962790000000",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Demo Customer"},
                                    "wa_id": customer_number,
                                }
                            ],
                            "messages": [
                                {
                                    "from": customer_number,
                                    "id": f"wamid.DEMO{uuid.uuid4().hex[:12]}",
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def main() -> None:
    text = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "I'd like to order 1 box of 6 Classic Chocolate Chip cookies, deliver to Sweifieh"
    )
    customer_number = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_CUSTOMER_NUMBER
    settings = get_settings()

    body = json.dumps(build_payload(text, DEMO_PHONE_NUMBER_ID, customer_number)).encode()
    signature = hmac.new(settings.meta_app_secret.encode(), body, hashlib.sha256).hexdigest()

    print(f"Simulating an inbound WhatsApp message from {customer_number} to staging: {text!r}")
    response = httpx.post(
        STAGING_WEBHOOK_URL,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
        timeout=15.0,
    )
    print(f"Webhook responded: {response.status_code}")
    if response.status_code == 403:
        print(
            "403 likely means local .env's META_APP_SECRET doesn't match staging's "
            "META_APP_SECRET value in Render — check both."
        )
    print("Check the staging worker logs / DB for the pipeline running end to end.")


if __name__ == "__main__":
    main()
