"""事件总线路由：主题 / 订阅 / 事件消息投递与重试。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.eventbus import (
    EventDeliveryReport,
    EventMessageCreate,
    SubscriptionCreate,
    SubscriptionStatusUpdate,
    TopicCreate,
    TopicStatusUpdate,
    TopicUpdate,
)
from app.services.eventbus import EventMessageService, SubscriptionService, TopicService

# ── 事件主题 ──
topics_router = APIRouter(prefix="/api/eventbus/topics", tags=["eventbus-topics"])


@topics_router.get("")
async def list_topics(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    keyword: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await TopicService.list_topics(session, limit, offset, status_filter, keyword)


@topics_router.post("", status_code=status.HTTP_201_CREATED)
async def create_topic(
    payload: TopicCreate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await TopicService.create_topic(session, payload, request)


@topics_router.get("/{topic_id}")
async def get_topic(
    topic_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await TopicService.get_topic(session, topic_id)


@topics_router.patch("/{topic_id}")
async def update_topic(
    topic_id: str, payload: TopicUpdate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await TopicService.update_topic(session, topic_id, payload, request)


@topics_router.patch("/{topic_id}/status")
async def update_topic_status(
    topic_id: str, payload: TopicStatusUpdate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await TopicService.update_status(session, topic_id, payload, request)


@topics_router.delete("/{topic_id}")
async def delete_topic(
    topic_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await TopicService.delete_topic(session, topic_id, request)


# ── 事件订阅 ──
subs_router = APIRouter(prefix="/api/eventbus/topics", tags=["eventbus-subscriptions"])


@subs_router.post("/{topic_id}/subscriptions", status_code=status.HTTP_201_CREATED)
async def create_subscription(
    topic_id: str, payload: SubscriptionCreate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await SubscriptionService.create_subscription(session, topic_id, payload, request)


@subs_router.get("/{topic_id}/subscriptions")
async def list_subscriptions(
    topic_id: str, request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await SubscriptionService.list_subscriptions(session, limit, offset,
                                                       topic_id, status_filter)


@subs_router.get("/subscriptions/{sub_id}")
async def get_subscription(
    sub_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await SubscriptionService.get_subscription(session, sub_id)


@subs_router.patch("/subscriptions/{sub_id}/status")
async def update_subscription_status(
    sub_id: str, payload: SubscriptionStatusUpdate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await SubscriptionService.update_status(session, sub_id, payload, request)


@subs_router.delete("/subscriptions/{sub_id}")
async def delete_subscription(
    sub_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await SubscriptionService.delete_subscription(session, sub_id, request)


# ── 重试队列（独立前缀避免与 {topic_id} 路径冲突）──
retry_router = APIRouter(prefix="/api/eventbus", tags=["eventbus-retry"])

# ── 事件消息与投递重试 ──
events_router = APIRouter(prefix="/api/eventbus/topics", tags=["eventbus-events"])


@events_router.post("/{topic_id}/events", status_code=status.HTTP_201_CREATED)
async def publish_event(
    topic_id: str, payload: EventMessageCreate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await EventMessageService.publish(session, topic_id, payload, request)


@events_router.get("/{topic_id}/events")
async def list_events(
    topic_id: str, request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await EventMessageService.list_messages(session, limit, offset,
                                                  topic_id, status_filter)


@events_router.get("/events/{msg_id}")
async def get_event(
    msg_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await EventMessageService.get_message(session, msg_id)


@events_router.post("/events/{msg_id}/delivery", status_code=status.HTTP_200_OK)
async def report_delivery(
    msg_id: str, payload: EventDeliveryReport, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await EventMessageService.report_delivery(session, msg_id, payload, request)


@retry_router.get("/retry-queue")
async def retry_queue(
    request: Request,
    topic_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await EventMessageService.list_retry_queue(session, topic_id)
