from reply_agent.llm.client import MODEL_HAIKU, MODEL_SONNET
from reply_agent.llm.routing import pick_generation_model


def test_high_confidence_short_conversation_uses_haiku():
    model = pick_generation_model(intent_confidence=0.95, conversation_turn_count=2, is_retry=False)
    assert model == MODEL_HAIKU


def test_mid_confidence_uses_sonnet():
    model = pick_generation_model(intent_confidence=0.55, conversation_turn_count=2, is_retry=False)
    assert model == MODEL_SONNET


def test_long_conversation_uses_sonnet_even_with_high_confidence():
    model = pick_generation_model(
        intent_confidence=0.95, conversation_turn_count=10, is_retry=False
    )
    assert model == MODEL_SONNET


def test_retry_always_uses_sonnet():
    model = pick_generation_model(intent_confidence=0.95, conversation_turn_count=1, is_retry=True)
    assert model == MODEL_SONNET


def test_low_confidence_below_band_still_uses_haiku():
    # Very low confidence isn't "ambiguous" — it's a clear low-confidence classification the
    # graph will likely escalate on self_check, not something Sonnet fixes.
    model = pick_generation_model(intent_confidence=0.1, conversation_turn_count=1, is_retry=False)
    assert model == MODEL_HAIKU
