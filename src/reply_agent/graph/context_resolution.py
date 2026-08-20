"""Resolves (or creates) the Customer and Conversation rows for an inbound message, before
the graph runs. thread_id is deterministic per (business, channel, customer) so the LangGraph
checkpointer always resumes the same conversation thread (Doc 2 Section 2.3: "keyed by
channel + customer ID").
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reply_agent.db.models import Business, ChannelType, Conversation, ConversationStatus, Customer


async def find_business_by_whatsapp_phone_number_id(
    session: AsyncSession, phone_number_id: str
) -> Business | None:
    return await session.scalar(
        select(Business).where(
            Business.channels_connected["whatsapp"]["phone_number_id"].astext == phone_number_id
        )
    )


def build_thread_id(
    business_id: uuid.UUID, channel: ChannelType, customer_channel_handle: str
) -> str:
    return f"{channel.value}:{business_id}:{customer_channel_handle}"


async def get_or_create_customer(
    session: AsyncSession, business_id: uuid.UUID, channel: ChannelType, channel_handle: str
) -> Customer:
    existing = await session.scalar(
        select(Customer).where(
            Customer.business_id == business_id,
            Customer.channel == channel,
            Customer.channel_handle == channel_handle,
        )
    )
    if existing:
        return existing

    customer = Customer(business_id=business_id, channel=channel, channel_handle=channel_handle)
    session.add(customer)
    await session.flush()
    return customer


async def get_or_create_conversation(
    session: AsyncSession, business_id: uuid.UUID, channel: ChannelType, customer: Customer
) -> Conversation:
    thread_id = build_thread_id(business_id, channel, customer.channel_handle)
    existing = await session.scalar(select(Conversation).where(Conversation.thread_id == thread_id))
    if existing:
        return existing

    conversation = Conversation(
        business_id=business_id,
        channel=channel,
        customer_id=customer.id,
        status=ConversationStatus.auto,
        thread_id=thread_id,
    )
    session.add(conversation)
    await session.flush()
    return conversation
