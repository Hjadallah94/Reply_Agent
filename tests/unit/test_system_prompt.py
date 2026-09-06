from reply_agent.llm.prompts.system import (
    BASE_SYSTEM_PROMPT,
    _reply_language_hint,
    build_system_prompt,
)


def _prompt(**overrides) -> str:
    defaults = {
        "business_name": "Amman Cookie Co",
        "brand_voice_examples": [],
        "retrieved_context": "",
    }
    return build_system_prompt(**{**defaults, **overrides})


def test_custom_rules_absent_by_default():
    prompt = _prompt()
    assert "Additional rules from the seller" not in prompt


def test_custom_rules_appear_when_provided():
    prompt = _prompt(custom_rules=["Never mention competitor prices."])
    assert "Additional rules from the seller" in prompt
    assert "Never mention competitor prices." in prompt


def test_multiple_custom_rules_each_get_their_own_line():
    prompt = _prompt(custom_rules=["Rule one.", "Rule two."])
    assert "- Rule one." in prompt
    assert "- Rule two." in prompt


def test_empty_custom_rules_list_is_same_as_none():
    assert "Additional rules" not in _prompt(custom_rules=[])
    assert "Additional rules" not in _prompt(custom_rules=None)


def test_order_confirmation_instruction_absent_by_default():
    prompt = _prompt()
    assert "before this order is treated as placed" not in prompt


def test_order_confirmation_instruction_appears_when_required():
    prompt = _prompt(require_order_confirmation=True)
    assert "before this order is treated as placed" in prompt
    assert "Do NOT say the order is placed or confirmed yet" in prompt


def test_order_confirmation_instruction_absent_when_explicitly_false():
    assert "before this order is treated as placed" not in _prompt(require_order_confirmation=False)


def test_base_prompt_names_arabizi_explicitly():
    # Souvenir-shop demo roadmap — customers sometimes write Arabic in Latin letters/digits
    # (e.g. "3" for ع); this must be named explicitly, not left to the code-switching line alone.
    assert "Arabizi" in BASE_SYSTEM_PROMPT
    assert "3" in BASE_SYSTEM_PROMPT and "ع" in BASE_SYSTEM_PROMPT


def test_base_prompt_instructs_asking_for_clarification_when_ambiguous():
    assert "ask a short, specific clarifying" in BASE_SYSTEM_PROMPT


def test_brand_voice_examples_do_not_override_the_customers_own_language():
    """Live-testing bug (souvenir-shop demo, 2026-09-06): an English customer message got an
    Arabic reply — the brand-voice examples (which happened to skew Arabic) pulled the reply's
    language along with its tone. This must say explicitly not to do that.
    """
    prompt = _prompt(brand_voice_examples=["Customer: hi\nSeller: مرحبا فيك!"])
    assert "don't copy their language" in prompt
    assert "language rule above" in prompt


def test_reply_language_hint_detects_arabic_script():
    assert "Arabic script" in _reply_language_hint("كم سعر العباية؟")
    assert "Reply in Arabic script" in _reply_language_hint("كم سعر العباية؟")


def test_reply_language_hint_treats_english_as_latin_script():
    hint = _reply_language_hint("how much is the Dead Sea one?")
    assert "Latin letters" in hint
    assert "Do NOT reply in Arabic script" in hint


def test_reply_language_hint_treats_arabizi_as_latin_script_too():
    # Doc 3 roadmap — Arabizi/Franco-Arabic is Latin-script Arabic; the point of this hint is
    # only ever "did the customer type Arabic script or not", not full language identification.
    hint = _reply_language_hint("kifak, 3andkun scarf b7wali 12 dinar?")
    assert "Latin letters" in hint


def test_language_hint_absent_from_prompt_when_no_customer_message_given():
    assert "IMPORTANT: The customer's latest message" not in _prompt()


def test_language_hint_present_when_customer_message_given():
    """Live-testing bug (souvenir-shop demo, 2026-09-06): even after fixing the brand-voice
    override, a plain English question ("how much is the Dead Sea one?") still got an Arabic
    reply — a rule stated once, early in a long system prompt, wasn't reliable enough. This is
    the deterministic, per-turn reinforcement placed last in the prompt instead.
    """
    prompt = _prompt(customer_message="how much is the Dead Sea one?")
    assert "IMPORTANT: The customer's latest message uses Latin letters only" in prompt
    # Placed after the retrieved context, not before — recency in the prompt matters for how
    # reliably a model actually follows an instruction.
    assert prompt.rindex("IMPORTANT: The customer's latest message") > prompt.rindex(
        "Retrieved context for this conversation"
    )
