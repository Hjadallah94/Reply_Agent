"""Demo/App-Review helper only — NOT part of the product. Simulates a real customer WhatsApp
message hitting our real, live webhook (same signature verification, same dedup, same queue,
same LangGraph pipeline a genuine Meta-sent webhook would trigger). Useful for recording a demo
of the actual send/receive flow without needing a second live phone number on the sandbox's
recipient allowlist.

Usage: uv run python scripts/demo_webhook_trigger.py "كم سعر العباية السودا؟"
       uv run python scripts/demo_webhook_trigger.py "Do you have the black abaya in size M?"
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

WEBHOOK_URL = "http://localhost:8811/webhooks/whatsapp"
DEMO_CUSTOMER_NUMBER = "962790005555"  # fake — never a real recipient, this never actually sends


def build_payload(text: str, phone_number_id: str) -> dict:
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
                                    "wa_id": DEMO_CUSTOMER_NUMBER,
                                }
                            ],
                            "messages": [
                                {
                                    "from": DEMO_CUSTOMER_NUMBER,
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
    text = sys.argv[1] if len(sys.argv) > 1 else "كم سعر العباية السودا؟"
    settings = get_settings()

    body = json.dumps(build_payload(text, settings.whatsapp_phone_number_id)).encode()
    signature = hmac.new(settings.meta_app_secret.encode(), body, hashlib.sha256).hexdigest()

    print(f"Simulating an inbound WhatsApp message: {text!r}")
    response = httpx.post(
        WEBHOOK_URL,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
        timeout=15.0,
    )
    print(f"Webhook responded: {response.status_code}")
    print("Watch the uvicorn and rq worker terminals for the pipeline running end to end.")


if __name__ == "__main__":
    main()
