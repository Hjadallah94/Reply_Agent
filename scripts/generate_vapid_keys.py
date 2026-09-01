"""One-off VAPID keypair generation for Web Push (Doc 3 Phase 6.6's push-notification piece,
notifications/push.py). Run once per environment; set the printed values as VAPID_PUBLIC_KEY/
VAPID_PRIVATE_KEY env vars (Render service Environment tab for staging/production, local .env
for local testing). Don't re-run casually — a new keypair invalidates every existing browser
subscription (base.html's registration script will silently stop delivering to them; they'd
need to click "Enable notifications" again).

Usage: uv run python scripts/generate_vapid_keys.py
"""

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid.utils import b64urlencode


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    # Raw/uncompressed form (base64url, unpadded) — what py_vapid.Vapid02.from_string() expects
    # back on read, and what a browser's PushManager.subscribe({applicationServerKey: ...})
    # expects for the public key.
    private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)

    print(f"VAPID_PUBLIC_KEY={b64urlencode(public_raw)}")
    print(f"VAPID_PRIVATE_KEY={b64urlencode(private_raw)}")
    print()
    print("Set both as env vars, plus VAPID_SUBJECT to a contact address the push services can")
    print("reach if they need to (required by the VAPID spec), e.g.:")
    print("VAPID_SUBJECT=mailto:support@optignosis.example")


if __name__ == "__main__":
    main()
