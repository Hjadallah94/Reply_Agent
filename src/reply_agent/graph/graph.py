"""Builds the LangGraph pipeline (Doc 2, Section 3.1, as corrected — see routers.py):

ingest_message -> load_context -> classify_intent -> estimate_delivery -> retrieve_knowledge
    -> generate_response -> self_check -> [confidence router]
        --send----> send_reply -> update_memory -> END
        --retry---> (loop back to retrieve_knowledge)
        --escalate-> escalate_to_owner -> update_memory -> END

Every message is drafted before the confidence router decides send vs. escalate — the risk
gate (Doc 2 Section 2.4) never skips retrieve_knowledge/generate_response, it only prevents
confidence_router from choosing "send" (Doc 1 Section 7: escalations always carry a draft).

estimate_delivery (Doc 2 Section 9.1) runs unconditionally in this topology, same as every
other node — it internally no-ops for every intent except place_order, rather than being a
second conditional-edges branch, so the graph keeps a single linear shape with one fan-out
point (self_check).
"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from reply_agent.graph.nodes.classify_intent import classify_intent
from reply_agent.graph.nodes.escalate_to_owner import escalate_to_owner
from reply_agent.graph.nodes.estimate_delivery import estimate_delivery
from reply_agent.graph.nodes.generate_response import generate_response
from reply_agent.graph.nodes.ingest_message import ingest_message
from reply_agent.graph.nodes.load_context import load_context
from reply_agent.graph.nodes.retrieve_knowledge import retrieve_knowledge
from reply_agent.graph.nodes.self_check import self_check
from reply_agent.graph.nodes.send_reply import send_reply
from reply_agent.graph.nodes.update_memory import update_memory
from reply_agent.graph.routers import confidence_router
from reply_agent.graph.state import GraphState
from reply_agent.memory.checkpointer import checkpointer_conn_string


def build_graph(checkpointer) -> StateGraph:
    builder = StateGraph(GraphState)

    builder.add_node("ingest_message", ingest_message)
    builder.add_node("load_context", load_context)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("estimate_delivery", estimate_delivery)
    builder.add_node("retrieve_knowledge", retrieve_knowledge)
    builder.add_node("generate_response", generate_response)
    builder.add_node("self_check", self_check)
    builder.add_node("send_reply", send_reply)
    builder.add_node("escalate_to_owner", escalate_to_owner)
    builder.add_node("update_memory", update_memory)

    builder.add_edge(START, "ingest_message")
    builder.add_edge("ingest_message", "load_context")
    builder.add_edge("load_context", "classify_intent")
    builder.add_edge("classify_intent", "estimate_delivery")
    builder.add_edge("estimate_delivery", "retrieve_knowledge")
    builder.add_edge("retrieve_knowledge", "generate_response")
    builder.add_edge("generate_response", "self_check")

    builder.add_conditional_edges(
        "self_check",
        confidence_router,
        {"send": "send_reply", "retry": "retrieve_knowledge", "escalate": "escalate_to_owner"},
    )

    builder.add_edge("send_reply", "update_memory")
    builder.add_edge("escalate_to_owner", "update_memory")
    builder.add_edge("update_memory", END)

    return builder.compile(checkpointer=checkpointer)


async def run_graph(initial_state: GraphState, thread_id: str) -> GraphState:
    async with AsyncPostgresSaver.from_conn_string(checkpointer_conn_string()) as checkpointer:
        compiled = build_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        return await compiled.ainvoke(initial_state, config=config)
