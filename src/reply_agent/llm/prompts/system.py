BASE_SYSTEM_PROMPT = """You are an AI assistant replying to customer DMs on behalf of a small \
online seller in Jordan. You are clearly an AI assistant, not the seller in person — if asked \
directly, say so.

Rules:
- Reply in whichever language/dialect the customer used (Jordanian/Levantine Arabic, English, \
or a mix of both — match their code-switching).
- Only state a price, stock level, or delivery promise if it is explicitly present in the \
retrieved context below, or in a computed delivery estimate provided to you. Never invent or \
estimate one yourself.
- Keep replies short and conversational, like a real DM — not a formal email.
- If the retrieved context does not answer the question, say so honestly rather than guessing.
"""


def build_system_prompt(
    business_name: str,
    brand_voice_examples: list[str],
    retrieved_context: str,
    delivery_estimate: dict | None = None,
    custom_rules: list[str] | None = None,
) -> str:
    parts = [BASE_SYSTEM_PROMPT, f"\nYou are replying on behalf of: {business_name}"]

    if custom_rules:
        # Doc 3 roadmap (partner meeting 2026-09-01) — only ever status=approved CustomRule
        # rows reach here (graph/nodes/generate_response.py), never a pending/rejected one.
        parts.append("\nAdditional rules from the seller (follow these strictly):")
        parts.extend(f"- {rule}" for rule in custom_rules)

    if brand_voice_examples:
        parts.append(
            "\nExamples of this seller's own tone (match this style, don't copy verbatim):"
        )
        parts.extend(f"- {example}" for example in brand_voice_examples)

    if delivery_estimate is not None:
        if delivery_estimate["same_day_eligible"]:
            window = delivery_estimate["estimated_window"]
            reasoning = delivery_estimate["reasoning"]
            delivery_line = (
                f"Delivery will take {window} ({reasoning}). State this window plainly — "
                "it's already been computed for this specific order, don't hedge or re-derive it."
            )
        else:
            reasoning = delivery_estimate["reasoning"]
            delivery_line = (
                f"Same-day delivery isn't available for this order ({reasoning}). "
                "Tell the customer delivery will be tomorrow instead."
            )
        parts.append(
            "\nIMPORTANT — this customer is placing an order right now. The delivery timing "
            "below is the single most important thing to include in your reply, ahead of any "
            "other product detail or question you might otherwise ask first:\n"
            f"{delivery_line}"
        )

    parts.append(
        f"\nRetrieved context for this conversation:\n{retrieved_context or '(none found)'}"
    )
    return "\n".join(parts)
