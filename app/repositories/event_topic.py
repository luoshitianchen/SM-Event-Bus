"""事件主题仓储层。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_topic import Topic


async def get_topic(session: AsyncSession, topic_id: str) -> Topic | None:
    result = await session.execute(select(Topic).where(Topic.id == topic_id))
    return result.scalar_one_or_none()


async def get_topic_by_name(session: AsyncSession, name: str) -> Topic | None:
    result = await session.execute(select(Topic).where(Topic.name == name))
    return result.scalar_one_or_none()


async def list_topics(
    session: AsyncSession, limit: int = 100, offset: int = 0,
    status: str | None = None, keyword: str | None = None,
) -> list[Topic]:
    stmt = select(Topic).order_by(Topic.created_at.desc())
    if status:
        stmt = stmt.where(Topic.status == status)
    if keyword:
        stmt = stmt.where(Topic.name.like(f"%{keyword}%"))
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_topics(
    session: AsyncSession, status: str | None = None, keyword: str | None = None,
) -> int:
    stmt = select(func.count(Topic.id))
    if status:
        stmt = stmt.where(Topic.status == status)
    if keyword:
        stmt = stmt.where(Topic.name.like(f"%{keyword}%"))
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def create_topic(session: AsyncSession, topic: Topic) -> Topic:
    session.add(topic)
    await session.commit()
    await session.refresh(topic)
    return topic


async def update_topic(session: AsyncSession, topic: Topic) -> Topic:
    await session.commit()
    await session.refresh(topic)
    return topic


async def delete_topic(session: AsyncSession, topic: Topic) -> None:
    await session.delete(topic)
    await session.commit()
