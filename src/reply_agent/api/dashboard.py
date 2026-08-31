"""Owner-facing dashboard (Doc 3 Phase 3): view conversations, approve/edit/send escalated
replies. Server-rendered with Jinja2 rather than a separate frontend build. Every route below
is gated by auth/dependencies.py's require_business_access — a logged-in user only ever sees
their own business, never anyone else's — and reads/writes through db/tenant_session.py, which
enforces that same boundary again at the database level (row-level security, not just app code).
"""

import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from reply_agent.auth.dependencies import get_current_user, require_business_access
from reply_agent.billing.usage import get_or_create_subscription, usage_summary
from reply_agent.db.models import (
    ApprovalRequest,
    ApprovalRequestStatus,
    Business,
    Conversation,
    ConversationStatus,
    Customer,
    Escalation,
    EscalationStatus,
    Message,
    MessageDirection,
    Order,
)
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.nodes.request_owner_approval import AUTO_APPROVAL_RESOLVED_BY
from reply_agent.graph.nodes.send_reply import send_reply
from reply_agent.knowledge.corrections import record_owner_correction

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/dashboard")
async def dashboard_redirect(request: Request):
    # No multi-business list — a user has exactly one business, straight there or to /login.
    user = await get_current_user(request)
    return RedirectResponse(url=f"/businesses/{user.business_id}/dashboard", status_code=303)


@router.get("/businesses/{business_id}/dashboard")
async def business_dashboard(
    request: Request, business: Business = Depends(require_business_access)
):
    async with tenant_session(business.id) as session:
        subscription = await get_or_create_subscription(session, business)
        usage = usage_summary(subscription)

        pending = (
            await session.scalars(
                select(Escalation)
                .join(Conversation)
                .where(
                    Conversation.business_id == business.id,
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

        pending_approval_records = (
            await session.scalars(
                select(ApprovalRequest)
                .join(Conversation)
                .where(
                    Conversation.business_id == business.id,
                    ApprovalRequest.status == ApprovalRequestStatus.pending,
                )
                .options(
                    selectinload(ApprovalRequest.conversation).selectinload(Conversation.customer)
                )
                .order_by(ApprovalRequest.created_at)
            )
        ).all()

        pending_approval_rows = [
            {
                "id": a.id,
                "customer_handle": a.conversation.customer.channel_handle,
                "channel": a.conversation.channel.value,
                "reasoning": a.reasoning,
            }
            for a in pending_approval_records
        ]

        # Adaptive autonomy's explainability surface (Doc 2 Section 9.4): read-only visibility
        # into what the system has started sending on its own, so the owner can always see why —
        # not a UI they act on, unlike the two sections above.
        recent_auto_approvals = (
            await session.scalars(
                select(ApprovalRequest)
                .join(Conversation)
                .where(
                    Conversation.business_id == business.id,
                    ApprovalRequest.resolved_by == AUTO_APPROVAL_RESOLVED_BY,
                    ApprovalRequest.resolution_time >= datetime.now(UTC) - timedelta(days=7),
                )
                .options(
                    selectinload(ApprovalRequest.conversation).selectinload(Conversation.customer)
                )
                .order_by(ApprovalRequest.resolution_time.desc())
            )
        ).all()

        recent_auto_approval_rows = [
            {
                "customer_handle": a.conversation.customer.channel_handle,
                "channel": a.conversation.channel.value,
                "estimated_window": a.estimated_window,
                "resolution_time": a.resolution_time.strftime("%Y-%m-%d %H:%M"),
            }
            for a in recent_auto_approvals
        ]

        conversations = (
            await session.scalars(
                select(Conversation)
                .where(Conversation.business_id == business.id)
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
            "pending_approvals": pending_approval_rows,
            "recent_auto_approvals": recent_auto_approval_rows,
            "conversations": conversation_rows,
        },
    )


@router.get("/businesses/{business_id}/dashboard/export")
async def export_conversations(business: Business = Depends(require_business_access)):
    async with tenant_session(business.id) as session:
        rows = (
            await session.execute(
                select(Message, Conversation, Customer)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .join(Customer, Conversation.customer_id == Customer.id)
                .where(Conversation.business_id == business.id)
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
async def escalation_detail(
    request: Request,
    escalation_id: uuid.UUID,
    business: Business = Depends(require_business_access),
):
    async with tenant_session(business.id) as session:
        escalation = await session.scalar(
            select(Escalation)
            .where(Escalation.id == escalation_id)
            .options(
                selectinload(Escalation.conversation).selectinload(Conversation.customer),
                selectinload(Escalation.conversation).selectinload(Conversation.messages),
            )
        )
        if escalation is None or escalation.conversation.business_id != business.id:
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
    escalation_id: uuid.UUID,
    reply_text: str = Form(...),
    business: Business = Depends(require_business_access),
):
    reply_text = reply_text.strip()
    if not reply_text:
        raise HTTPException(status_code=400, detail="Reply text is required")

    async with tenant_session(business.id) as session:
        escalation = await session.scalar(
            select(Escalation)
            .where(Escalation.id == escalation_id)
            .options(selectinload(Escalation.conversation))
        )
        if escalation is None or escalation.conversation.business_id != business.id:
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

        # Owner-correction feedback loop (Doc 1 Section 7) — only when the owner actually sent
        # something different from the agent's own draft (including drafting nothing at all, a
        # capability-gap escalation): approving a draft unchanged isn't a correction, it's
        # confirmation the agent already had it right, and doesn't need to teach it anything.
        if reply_text != (escalation.drafted_reply or ""):
            customer_message = await session.scalar(
                select(Message)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.direction == MessageDirection.inbound,
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            if customer_message is not None:
                await record_owner_correction(
                    session,
                    business_id=business.id,
                    customer_message=customer_message.text,
                    corrected_reply=reply_text,
                    escalation_id=escalation.id,
                )

        escalation.status = EscalationStatus.resolved
        escalation.resolved_by = "owner"
        escalation.resolution_text = reply_text
        escalation.resolution_time = datetime.now(UTC)
        conversation.status = ConversationStatus.auto

    return RedirectResponse(url=f"/businesses/{business.id}/dashboard", status_code=303)


@router.get("/businesses/{business_id}/dashboard/approvals/{approval_id}")
async def approval_detail(
    request: Request,
    approval_id: uuid.UUID,
    business: Business = Depends(require_business_access),
):
    async with tenant_session(business.id) as session:
        approval = await session.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .options(
                selectinload(ApprovalRequest.conversation).selectinload(Conversation.customer),
                selectinload(ApprovalRequest.conversation).selectinload(Conversation.messages),
            )
        )
        if approval is None or approval.conversation.business_id != business.id:
            raise HTTPException(status_code=404, detail="Approval request not found")

        conversation = approval.conversation
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
        "approval.html",
        {
            "business": business,
            "approval": approval,
            "customer_handle": conversation.customer.channel_handle,
            "channel": conversation.channel.value,
            "messages": messages,
            "reject_default": (
                "Sorry, that delivery time isn't approved — we can get it to you tomorrow instead."
            ),
        },
    )


@router.post("/businesses/{business_id}/dashboard/approvals/{approval_id}/approve")
async def approve_approval(
    approval_id: uuid.UUID,
    reply_text: str = Form(...),
    business: Business = Depends(require_business_access),
):
    reply_text = reply_text.strip()
    if not reply_text:
        raise HTTPException(status_code=400, detail="Reply text is required")

    async with tenant_session(business.id) as session:
        approval = await session.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .options(selectinload(ApprovalRequest.conversation))
        )
        if approval is None or approval.conversation.business_id != business.id:
            raise HTTPException(status_code=404, detail="Approval request not found")
        if approval.status != ApprovalRequestStatus.pending:
            raise HTTPException(status_code=409, detail="Approval request already resolved")

        conversation = approval.conversation

        await send_reply(
            {
                "channel": conversation.channel.value,
                "business_id": str(conversation.business_id),
                "thread_id": conversation.thread_id,
                "draft_reply": {"text": reply_text},
            }
        )

        session.add(
            Message(
                conversation_id=conversation.id,
                direction=MessageDirection.outbound,
                text=reply_text,
                model_used="owner",
            )
        )

        # Same owner-correction gate as resolve_escalation — approving a draft unchanged isn't
        # a correction, editing it before sending is.
        if reply_text != (approval.drafted_reply or ""):
            customer_message = await session.scalar(
                select(Message)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.direction == MessageDirection.inbound,
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            if customer_message is not None:
                await record_owner_correction(
                    session,
                    business_id=business.id,
                    customer_message=customer_message.text,
                    corrected_reply=reply_text,
                    approval_id=approval.id,
                )

        approval.status = ApprovalRequestStatus.approved
        approval.resolved_by = "owner"
        approval.resolution_time = datetime.now(UTC)
        # Adaptive autonomy's training signal (Doc 2 Section 9.4, graph/nodes/
        # request_owner_approval.py's _matches_learned_pattern) — only an unedited approval
        # counts toward earning auto-approval for this (business, estimated_window) pattern.
        approval.sent_unchanged = reply_text == (approval.drafted_reply or "")
        conversation.status = ConversationStatus.auto

    return RedirectResponse(url=f"/businesses/{business.id}/dashboard", status_code=303)


@router.post("/businesses/{business_id}/dashboard/approvals/{approval_id}/reject")
async def reject_approval(
    approval_id: uuid.UUID,
    reply_text: str = Form(...),
    business: Business = Depends(require_business_access),
):
    reply_text = reply_text.strip()
    if not reply_text:
        raise HTTPException(status_code=400, detail="Reply text is required")

    async with tenant_session(business.id) as session:
        approval = await session.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .options(selectinload(ApprovalRequest.conversation))
        )
        if approval is None or approval.conversation.business_id != business.id:
            raise HTTPException(status_code=404, detail="Approval request not found")
        if approval.status != ApprovalRequestStatus.pending:
            raise HTTPException(status_code=409, detail="Approval request already resolved")

        conversation = approval.conversation

        await send_reply(
            {
                "channel": conversation.channel.value,
                "business_id": str(conversation.business_id),
                "thread_id": conversation.thread_id,
                "draft_reply": {"text": reply_text},
            }
        )

        session.add(
            Message(
                conversation_id=conversation.id,
                direction=MessageDirection.outbound,
                text=reply_text,
                model_used="owner",
            )
        )

        # Declining a same-day commitment isn't a phrasing correction (see plan's Design
        # decisions) — no record_owner_correction call here, unlike the approve route.

        # The Order row estimate_delivery already wrote is still showing the declined same-day
        # promise — update it so it reflects what the customer was actually told, and so it
        # drops out of estimate_delivery's backlog COUNT (which filters on delivery_status ==
        # "pending") for the rest of today.
        if approval.order_reference:
            order = await session.scalar(
                select(Order).where(
                    Order.business_id == business.id,
                    Order.order_reference == approval.order_reference,
                )
            )
            if order is not None:
                order.delivery_status = "declined"
                order.delivery_window_promised = "tomorrow"

        approval.status = ApprovalRequestStatus.rejected
        approval.resolved_by = "owner"
        approval.resolution_time = datetime.now(UTC)
        # A reject is never "unchanged" — set explicitly (rather than left null) so it reads
        # unambiguously alongside sent_unchanged=True/False on approved rows.
        approval.sent_unchanged = False
        conversation.status = ConversationStatus.auto

    return RedirectResponse(url=f"/businesses/{business.id}/dashboard", status_code=303)
