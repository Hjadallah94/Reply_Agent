"""Owner-facing dashboard (Doc 3 Phase 3): view conversations, approve/edit/send escalated
replies. Server-rendered with Jinja2 rather than a separate frontend build — an internal MVP
tool, not yet behind auth, so don't expose this route publicly as-is.
"""

import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from reply_agent.billing.usage import get_or_create_subscription, usage_summary
from reply_agent.db.models import (
    Business,
    Conversation,
    ConversationStatus,
    Customer,
    Escalation,
    EscalationStatus,
    Message,
    MessageDirection,
)
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.nodes.send_reply import send_reply

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/dashboard")
async def list_businesses(request: Request):
    async with get_sessionmaker()() as session:
        businesses = (await session.scalars(select(Business).order_by(Business.name))).all()
        pending_counts = dict(
            (
                await session.execute(
                    select(Conversation.business_id, func.count())
                    .join(Escalation, Escalation.conversation_id == Conversation.id)
                    .where(Escalation.status == EscalationStatus.pending)
                    .group_by(Conversation.business_id)
                )
            ).all()
        )

    rows = [
        {
            "id": b.id,
            "name": b.name,
            "plan_tier": b.plan_tier,
            "pending_count": pending_counts.get(b.id, 0),
        }
        for b in businesses
    ]
    return templates.TemplateResponse(request, "businesses.html", {"businesses": rows})


@router.get("/businesses/{business_id}/dashboard")
async def business_dashboard(request: Request, business_id: uuid.UUID):
    async with get_sessionmaker()() as session:
        business = await session.get(Business, business_id)
        if business is None:
            raise HTTPException(status_code=404, detail="Business not found")

        subscription = await get_or_create_subscription(session, business)
        await session.commit()
        usage = usage_summary(subscription)

        pending = (
            await session.scalars(
                select(Escalation)
                .join(Conversation)
                .where(
                    Conversation.business_id == business_id,
                    Escalation.status == EscalationStatus.pending,
                )
                .options(selectinload(Escalation.conversation).selectinload(Conversation.customer))
                .order_by(Escalation.created_at)
            )
        ).all()

        pending_rows = [
            {
                "id": e.id,
                "customer_handle": e.conversation.customer.channel_handle,
                "channel": e.conversation.channel.value,
                "reason": e.reason,
            }
            for e in pending
        ]

        conversations = (
            await session.scalars(
                select(Conversation)
                .where(Conversation.business_id == business_id)
                .options(selectinload(Conversation.customer), selectinload(Conversation.messages))
                .order_by(Conversation.updated_at.desc())
                .limit(30)
            )
        ).all()

        conversation_rows = [
            {
                "customer_handle": c.customer.channel_handle,
                "status": c.status.value,
                "last_message_text": c.messages[-1].text if c.messages else None,
            }
            for c in conversations
        ]

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "business": business,
            "usage": usage,
            "pending_escalations": pending_rows,
            "conversations": conversation_rows,
        },
    )


@router.get("/businesses/{business_id}/dashboard/export")
async def export_conversations(business_id: uuid.UUID):
    async with get_sessionmaker()() as session:
        business = await session.get(Business, business_id)
        if business is None:
            raise HTTPException(status_code=404, detail="Business not found")

        rows = (
            await session.execute(
                select(Message, Conversation, Customer)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .join(Customer, Conversation.customer_id == Customer.id)
                .where(Conversation.business_id == business_id)
                .order_by(Customer.channel_handle, Message.created_at)
            )
        ).all()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Conversations"
    headers = [
        "Customer",
        "Channel",
        "From",
        "Message",
        "Intent",
        "Handled by",
        "Conversation status",
        "Sent at (UTC)",
    ]
    sheet.append(headers)
    for message, conversation, customer in rows:
        sheet.append(
            [
                customer.channel_handle,
                conversation.channel.value,
                "Customer" if message.direction == MessageDirection.inbound else "Agent",
                message.text,
                message.intent_label or "",
                message.model_used or "",
                conversation.status.value,
                message.created_at.strftime("%Y-%m-%d %H:%M"),
            ]
        )

    for i, width in enumerate([16, 11, 10, 60, 22, 16, 16, 16], start=1):
        sheet.column_dimensions[get_column_letter(i)].width = width
    sheet.freeze_panes = "A2"

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    safe_name = "".join(c if c.isalnum() else "_" for c in business.name)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_conversations.xlsx"'},
    )


@router.get("/businesses/{business_id}/dashboard/escalations/{escalation_id}")
async def escalation_detail(request: Request, business_id: uuid.UUID, escalation_id: uuid.UUID):
    async with get_sessionmaker()() as session:
        business = await session.get(Business, business_id)
        if business is None:
            raise HTTPException(status_code=404, detail="Business not found")

        escalation = await session.scalar(
            select(Escalation)
            .where(Escalation.id == escalation_id)
            .options(
                selectinload(Escalation.conversation).selectinload(Conversation.customer),
                selectinload(Escalation.conversation).selectinload(Conversation.messages),
            )
        )
        if escalation is None or escalation.conversation.business_id != business_id:
            raise HTTPException(status_code=404, detail="Escalation not found")

        conversation = escalation.conversation
        messages = [
            {
                "direction": m.direction.value,
                "text": m.text,
                "created_at": m.created_at.strftime("%Y-%m-%d %H:%M"),
            }
            for m in conversation.messages
        ]

    return templates.TemplateResponse(
        request,
        "escalation.html",
        {
            "business": business,
            "escalation": escalation,
            "customer_handle": conversation.customer.channel_handle,
            "channel": conversation.channel.value,
            "messages": messages,
        },
    )


@router.post("/businesses/{business_id}/dashboard/escalations/{escalation_id}/resolve")
async def resolve_escalation(
    business_id: uuid.UUID,
    escalation_id: uuid.UUID,
    reply_text: str = Form(...),
):
    reply_text = reply_text.strip()
    if not reply_text:
        raise HTTPException(status_code=400, detail="Reply text is required")

    async with get_sessionmaker()() as session:
        escalation = await session.scalar(
            select(Escalation)
            .where(Escalation.id == escalation_id)
            .options(selectinload(Escalation.conversation))
        )
        if escalation is None or escalation.conversation.business_id != business_id:
            raise HTTPException(status_code=404, detail="Escalation not found")
        if escalation.status != EscalationStatus.pending:
            raise HTTPException(status_code=409, detail="Escalation already resolved")

        conversation = escalation.conversation

        # Reuses the same channel-dispatch code a real auto-send would go through, rather
        # than duplicating the WhatsApp/Instagram/Messenger match statement here.
        await send_reply(
            {
                "channel": conversation.channel.value,
                "business_id": str(conversation.business_id),
                "thread_id": conversation.thread_id,
                "draft_reply": {"text": reply_text},
            }
        )

        # update_memory only logs an outbound message when route == "send" (graph/nodes/
        # update_memory.py) — escalated turns skip that, so this is the first record of it.
        session.add(
            Message(
                conversation_id=conversation.id,
                direction=MessageDirection.outbound,
                text=reply_text,
                model_used="owner",
            )
        )
        escalation.status = EscalationStatus.resolved
        escalation.resolved_by = "owner"
        escalation.resolution_text = reply_text
        escalation.resolution_time = datetime.now(UTC)
        conversation.status = ConversationStatus.auto

        await session.commit()

    return RedirectResponse(url=f"/businesses/{business_id}/dashboard", status_code=303)
