"""事件订阅仓储层。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_subscription import Subscription


async def get_subscription(session: AsyncSession, sub_id: str) -> Subscription | None:
    result = await session.execute(select(Subscription).where(Subscription.id == sub_id))
    return result.scalar_one_or_none()


async def list_subscriptions(
    session: AsyncSession, limit: int = 100, offset: int = 0,
    topic_id: str | None = None, status: str | None = None,
) -> list[Subscription]:
    stmt = select(Subscription).order_by(Subscription.created_at.desc())
    if topic_id:
        stmt = stmt.where(Subscription.topic_id == topic_id)
    if status:
        stmt = stmt.where(Subscription.status == status)
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_subscriptions(
    session: AsyncSession, topic_id: str | None = None, status: str | None = None,
) -> int:
    stmt = select(func.count(Subscription.id))
    if topic_id:
        stmt = stmt.where(Subscription.topic_id == topic_id)
    if status:
        stmt = stmt.where(Subscription.status == status)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def create_subscription(session: AsyncSession, sub: Subscription) -> Subscription:
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


async def update_subscription(session: AsyncSession, sub: Subscription) -> Subscription:
    await session.commit()
    await session.refresh(sub)
    return sub


async def delete_subscription(session: AsyncSession, sub: Subscription) -> None:
    await session.delete(sub)
    await session.commit()
