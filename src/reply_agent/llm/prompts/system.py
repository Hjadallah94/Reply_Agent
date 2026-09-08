import re

# Doc 3 roadmap (found live, souvenir-shop demo 2026-09-06) — a general "reply in the
# customer's language" rule, even after reinforcing it against the brand-voice examples, still
# wasn't reliable enough on its own: a plain English question ("how much is the Dead Sea one?")
# still came back with an Arabic-script reply. A rule stated once in a long system prompt is
# easy for a model to under-weight over other signals; a short, deterministic, per-turn fact
# placed right before generation (see build_system_prompt's use of this) is much harder to
# miss. This only determines whether Arabic *script* characters are present — not the
# customer's actual language/dialect (Arabizi and English are both Latin-script, and telling
# them apart isn't needed here: the observed bug is specifically Latin-script input getting an
# Arabic-script reply, not confusion between English and Arabizi).
_ARABIC_SCRIPT_PATTERN = re.compile(r"[؀-ۿ]")


def _reply_language_hint(customer_message: str) -> str:
    if _ARABIC_SCRIPT_PATTERN.search(customer_message):
        return (
            "The customer's latest message uses Arabic script. Reply in Arabic script "
            "(matching their dialect), not English."
        )
    return (
        "The customer's latest message uses Latin letters only (English or Arabizi/Franco-"
        "Arabic, not Arabic script) — reply using Latin letters too. Do NOT reply in Arabic "
        "script for this message, even if earlier context or examples happen to be in Arabic."
    )


BASE_SYSTEM_PROMPT = """You are an AI assistant replying to customer DMs on behalf of a small \
online seller in Jordan. You are clearly an AI assistant, not the seller in person — if asked \
directly, say so.

Rules:
- Reply in whichever language/dialect the customer used (Jordanian/Levantine Arabic, English, \
or a mix of both — match their code-switching). This includes Arabizi/Franco-Arabic — Arabic \
written with Latin letters and numbers standing in for letters with no direct equivalent (e.g. \
"3" for ع, "7" for ح, "2" for ء/أ, as in "shu as3arkom" for "شو أسعاركم"). Understand it exactly \
as you would the Arabic script it stands for, and reply in whichever of the three the customer \
actually used.
- Only state a price, stock level, or delivery promise if it is explicitly present in the \
retrieved context below, or in a computed delivery estimate provided to you. Never invent or \
estimate one yourself.
- Keep replies short and conversational, like a real DM — not a formal email.
- If the retrieved context does not answer the question, say so honestly rather than guessing.
- If you genuinely can't tell what the customer means — which language they're using, which \
product they mean, or what they're actually asking for — ask a short, specific clarifying \
question instead of guessing. Only do this when actually unclear, not as a way to avoid \
answering a question you could otherwise answer.
"""


def build_system_prompt(
    business_name: str,
    brand_voice_examples: list[str],
    retrieved_context: str,
    customer_message: str = "",
    delivery_estimate: dict | None = None,
    custom_rules: list[str] | None = None,
    require_order_confirmation: bool = False,
    will_escalate_for_capability_gap: bool = False,
    open_risk_escalation_reasons: list[str] | None = None,
) -> str:
    parts = [BASE_SYSTEM_PROMPT, f"\nYou are replying on behalf of: {business_name}"]

    if custom_rules:
        # Doc 3 roadmap (partner meeting 2026-09-01) — only ever status=approved CustomRule
        # rows reach here (graph/nodes/generate_response.py), never a pending/rejected one.
        parts.append("\nAdditional rules from the seller (follow these strictly):")
        parts.extend(f"- {rule}" for rule in custom_rules)

    if brand_voice_examples:
        # Live-testing found a real bug this fixes: examples happening to skew toward one
        # language (a real seller's own samples will often lean Arabic, since that's who they
        # mostly talk to) pulled replies toward that language even for an English-speaking
        # customer, overriding the "reply in the customer's own language" rule above. These
        # examples are for TONE ONLY — never let them decide which language to reply in.
        parts.append(
            "\nExamples of this seller's own tone (match the warmth/style, don't copy "
            "verbatim, and don't copy their language either — these examples may be in a "
            "different language than this customer is using; always follow the language rule "
            "above, not whatever language happens to dominate these examples):"
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

    if require_order_confirmation:
        # Doc 3 roadmap (partner meeting 2026-09-01, order confirmation layer) — the customer
        # hasn't confirmed this order yet, so the draft must ask rather than declare.
        parts.append(
            "\nIMPORTANT — before this order is treated as placed, you must first summarize "
            "exactly what you understood (the items, the price, the delivery address, and the "
            "delivery window above) and explicitly ask the customer to confirm it's correct or "
            "tell you what to fix. Do NOT say the order is placed or confirmed yet — that only "
            "happens once the customer confirms in a follow-up message."
        )

    if will_escalate_for_capability_gap:
        # Found live, 12-message Petra Treasures conversation test (2026-09-07): a draft for an
        # order-cancellation request the pipeline structurally can't act on (risk_rules.py's
        # NO_CAPABILITY_LABELS) opened with "No problem! Cancelling the scarf + other order..." —
        # confident, present-tense language for an action that never actually happens. This
        # draft is only ever shown to the owner to review and send themselves (never auto-sent —
        # that's the definition of a capability-gap escalation), so it must read that way, not
        # as a completed or promised action.
        parts.append(
            "\nIMPORTANT — you cannot actually perform this request; there is no system "
            "capability for it yet. This draft will be shown to the business owner to review "
            "and send themselves, not sent to the customer automatically. Do NOT write as if "
            "the action has already happened or will definitely happen (e.g. never say "
            "'cancelling your order now' or 'I've updated that') — acknowledge the request and "
            "say the owner will follow up on it directly, without confirming anything you have "
            "no way to actually do."
        )

    if open_risk_escalation_reasons:
        # Doc 3 roadmap (real gap found live, 12-message Petra Treasures conversation test,
        # 2026-09-07) — a discount request correctly escalated under the price_negotiation risk
        # category (the owner explicitly wants to decide those, not the agent), but the very
        # next customer message — a different topic — produced an auto-sent reply that also
        # addressed the discount inline, resolving it without the owner ever seeing it. The
        # risk gate only looks at the current message's own classified intent; this tells the
        # model plainly not to quietly resolve an already-escalated topic just because it
        # resurfaces in conversation_history.
        reasons_text = "; ".join(open_risk_escalation_reasons)
        parts.append(
            f"\nIMPORTANT — the following topic(s) from earlier in this conversation are still "
            f"waiting on the owner's decision and have NOT been resolved: {reasons_text}. Do "
            "NOT answer, resolve, or restate a decision on any of these specific topics "
            "yourself, even if the customer brings it up again — if it comes up, just say it's "
            "still waiting on the owner. You can still help with anything else in their message."
        )

    parts.append(
        f"\nRetrieved context for this conversation:\n{retrieved_context or '(none found)'}"
    )

    if customer_message:
        # Placed last, deliberately — a fact stated right before generation is far more
        # reliably followed than the same rule stated once, much earlier, in a long system
        # prompt (see the module-level comment on _reply_language_hint for the live bug that
        # motivated this).
        parts.append(f"\nIMPORTANT: {_reply_language_hint(customer_message)}")
    return "\n".join(parts)
