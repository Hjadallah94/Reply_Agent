"""Phone number normalization so a seller's order sheet matches how WhatsApp actually sends
customer numbers (Customer.channel_handle, e.g. "962791234567" — no leading +). Order lookup
in retrieve_knowledge.py is an exact match on this normalized form, so both sides (ingestion
here, lookup there) must agree on it.
"""

import re


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", str(raw))

    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("962"):
        return digits
    if digits.startswith("0"):
        return "962" + digits[1:]
    if len(digits) == 9 and digits.startswith("7"):
        # Common Excel gotcha: a phone column formatted as a number strips the leading 0
        # (Jordanian mobiles are 07XXXXXXXX in the sheet -> stored as 7XXXXXXXX).
        return "962" + digits
    return digits
