"""Builds the LangGraph pipeline (Doc 2, Section 3.1, as corrected — see routers.py):

ingest_message -> load_context -> [load_context_router]
    --away-----------------> send_away_reply -> update_memory -> END
    --pending_confirmation-> classify_confirmation_reply -> [order_confirmation_router]
        --confirmed-> generate_response (rejoins the normal path below)
        --declined--> send_order_catalog_reply -> update_memory -> END
        --unclear---> escalate_to_owner -> update_memory -> END
    --continue-------------> classify_intent -> estimate_delivery -> retrieve_knowledge
        -> generate_response -> self_check -> [confidence router]
            --send----> send_reply -> update_memory -> END
            --retry---> (loop back to retrieve_knowledge)
            --escalate-> escalate_to_owner -> update_memory -> END
            --approve-> request_owner_approval -> update_memory -> END

Every message is drafted before the confidence router decides send vs. escalate — the risk
gate (Doc 2 Section 2.4) never skips retrieve_knowledge/generate_response, it only prevents
confidence_router from choosing "send" (Doc 1 Section 7: escalations always carry a draft).

estimate_delivery (Doc 2 Section 9.1) runs unconditionally in this topology, same as every
other node — it internally no-ops for every intent except place_order, rather than being a
second conditional-edges branch, so the graph keeps a single linear shape with one fan-out
point (self_check).

request_owner_approval (Doc 2 Section 9.2) is a fourth branch off that same fan-out point,
alongside send/retry/escalate — a same-day delivery commitment that IS well-grounded (unlike
escalation) but still needs the owner's sign-off before it reaches the customer. Doc 3 roadmap
(order confirmation layer): it now only fires once the customer has actually confirmed the
order (routers.py's needs_owner_approval) — see below.

load_context_router (Doc 3 roadmap, "I'm not available today" + order confirmation layer) is
the graph's *second* fan-out point, deliberately breaking the "every node runs unconditionally"
pattern above: while a business is away, every message gets the same away-reply, so there's
nothing useful for classification/retrieval/generation/self-check to do — skipping them
outright, rather than having each one no-op internally, is a real cost saving, not just simpler
code. Its second branch (pending_confirmation) is the same idea applied to the order
confirmation layer: when the customer has an unconfirmed order waiting on their reply, there's
nothing useful for classify_intent to do with what's likely just "yes"/"no" text either.

order_confirmation_router (Doc 3 roadmap) is the graph's *third* fan-out point, right after
classify_confirmation_reply — see routers.py for the full reasoning on each of its three
branches. Note that its "confirmed" branch targets generate_response directly, the same node
the normal "continue" path also reaches via retrieve_knowledge — a node can have more than one
incoming edge in LangGraph, and everything generate_response needs is already known by then
(classify_confirmation_reply sets a synthetic intent + delivery_estimate), so there's no reason
to re-run classify_intent/estimate_delivery/retrieve_knowledge on a reply that's already been
matched to its order.
"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from reply_agent.graph.nodes.classify_confirmation_reply import classify_confirmation_reply
from reply_agent.graph.nodes.classify_intent import classify_intent
from reply_agent.graph.nodes.escalate_to_owner import escalate_to_owner
from reply_agent.graph.nodes.estimate_delivery import estimate_delivery
from reply_agent.graph.nodes.generate_response import generate_response
from reply_agent.graph.nodes.ingest_message import ingest_message
from reply_agent.graph.nodes.load_context import load_context
from reply_agent.graph.nodes.request_owner_approval import request_owner_approval
from reply_agent.graph.nodes.retrieve_knowledge import retrieve_knowledge
from reply_agent.graph.nodes.self_check import self_check
from reply_agent.graph.nodes.send_away_reply import send_away_reply
from reply_agent.graph.nodes.send_order_catalog_reply import send_order_catalog_reply
from reply_agent.graph.nodes.send_reply import send_reply
from reply_agent.graph.nodes.update_memory import update_memory
from reply_agent.graph.routers import (
    confidence_router,
    load_context_router,
    order_confirmation_router,
)
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
    builder.add_node("send_away_reply", send_away_reply)
    builder.add_node("escalate_to_owner", escalate_to_owner)
    builder.add_node("request_owner_approval", request_owner_approval)
    builder.add_node("classify_confirmation_reply", classify_confirmation_reply)
    builder.add_node("send_order_catalog_reply", send_order_catalog_reply)
    builder.add_node("update_memory", update_memory)

    builder.add_edge(START, "ingest_message")
    builder.add_edge("ingest_message", "load_context")

    builder.add_conditional_edges(
        "load_context",
        load_context_router,
        {
            "away": "send_away_reply",
            "pending_confirmation": "classify_confirmation_reply",
            "continue": "classify_intent",
        },
    )

    builder.add_conditional_edges(
        "classify_confirmation_reply",
        order_confirmation_router,
        {
            "confirmed": "generate_response",
            "declined": "send_order_catalog_reply",
            "unclear": "escalate_to_owner",
        },
    )

    builder.add_edge("classify_intent", "estimate_delivery")
    builder.add_edge("estimate_delivery", "retrieve_knowledge")
    builder.add_edge("retrieve_knowledge", "generate_response")
    builder.add_edge("generate_response", "self_check")

    builder.add_conditional_edges(
        "self_check",
        confidence_router,
        {
            "send": "send_reply",
            "retry": "retrieve_knowledge",
            "escalate": "escalate_to_owner",
            "approve": "request_owner_approval",
        },
    )

    builder.add_edge("send_reply", "update_memory")
    builder.add_edge("send_away_reply", "update_memory")
    builder.add_edge("escalate_to_owner", "update_memory")
    builder.add_edge("request_owner_approval", "update_memory")
    builder.add_edge("send_order_catalog_reply", "update_memory")
    builder.add_edge("update_memory", END)

    return builder.compile(checkpointer=checkpointer)


async def run_graph(initial_state: GraphState, thread_id: str) -> GraphState:
    async with AsyncPostgresSaver.from_conn_string(checkpointer_conn_string()) as checkpointer:
        compiled = build_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        return await compiled.ainvoke(initial_state, config=config)
