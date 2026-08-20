"""Model routing per Doc 2, Section 3.3: Haiku is the default; Sonnet is reserved for the
minority of turns that need it (mid-confidence classification, long/ambiguous threads,
or a self_check-triggered retry). classify_intent and self_check always use Haiku per the
Doc 2 node reference table — only generate_response routes between the two.
"""

from reply_agent.llm.client import MODEL_HAIKU, MODEL_SONNET

CONFIDENCE_LOW = 0.4
CONFIDENCE_HIGH = 0.75
LONG_CONVERSATION_TURNS = 8


def pick_generation_model(
    *, intent_confidence: float, conversation_turn_count: int, is_retry: bool
) -> str:
    if is_retry:
        return MODEL_SONNET
    if conversation_turn_count >= LONG_CONVERSATION_TURNS:
        return MODEL_SONNET
    if CONFIDENCE_LOW <= intent_confidence < CONFIDENCE_HIGH:
        return MODEL_SONNET
    return MODEL_HAIKU
