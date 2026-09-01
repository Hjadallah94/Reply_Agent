from reply_agent.llm.prompts.system import build_system_prompt


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
