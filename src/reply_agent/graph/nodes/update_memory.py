from sqlalchemy import select

from reply_agent.db.models import Conversation, Message, MessageDirection
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.state import GraphState


async def update_memory(state: GraphState) -> dict:
    draft = state.get("draft_reply")
    if draft is None or state.get("route") != "send":
        # Escalations already wrote their own record in escalate_to_owner; nothing sent yet.
        return {}

    intent = state.get("intent", {})

    async with get_sessionmaker()() as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == state["thread_id"])
        )
        session.add(
            Message(
                conversation_id=conversation.id,
                direction=MessageDirection.outbound,
                text=draft["text"],
                intent_label=intent.get("label"),
                model_used=draft["model_used"],
            )
        )
        await session.commit()

    return {}
