"""事件消息仓储层：投递状态查询与重试。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_message import EventMessage


async def get_message(session: AsyncSession, msg_id: str) -> EventMessage | None:
    result = await session.execute(select(EventMessage).where(EventMessage.id == msg_id))
    return result.scalar_one_or_none()


async def list_messages(
    session: AsyncSession, limit: int = 100, offset: int = 0,
    topic_id: str | None = None, status: str | None = None,
) -> list[EventMessage]:
    stmt = select(EventMessage).order_by(EventMessage.created_at.desc())
    if topic_id:
        stmt = stmt.where(EventMessage.topic_id == topic_id)
    if status:
        stmt = stmt.where(EventMessage.status == status)
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_pending_retry(
    session: AsyncSession, topic_id: str | None = None, limit: int = 100,
) -> list[EventMessage]:
    """查询待重试或待投递的消息。"""
    stmt = select(EventMessage).where(EventMessage.status.in_(["pending", "failed"]))
    if topic_id:
        stmt = stmt.where(EventMessage.topic_id == topic_id)
    stmt = stmt.order_by(EventMessage.retry_count.asc(), EventMessage.created_at.asc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_messages(
    session: AsyncSession, topic_id: str | None = None, status: str | None = None,
) -> int:
    stmt = select(func.count(EventMessage.id))
    if topic_id:
        stmt = stmt.where(EventMessage.topic_id == topic_id)
    if status:
        stmt = stmt.where(EventMessage.status == status)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def create_message(session: AsyncSession, msg: EventMessage) -> EventMessage:
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


async def update_message(session: AsyncSession, msg: EventMessage) -> EventMessage:
    await session.commit()
    await session.refresh(msg)
    return msg


async def delete_message(session: AsyncSession, msg: EventMessage) -> None:
    await session.delete(msg)
    await session.commit()
