"""事件总线服务层：主题 / 订阅 / 事件投递与重试全生命周期管理。"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import internal_write_allowed
from app.models.event_message import EventMessage
from app.models.event_subscription import Subscription
from app.models.event_topic import Topic
from app.repositories import event_message as msg_repo
from app.repositories import event_subscription as sub_repo
from app.repositories import event_topic as topic_repo
from app.schemas.eventbus import (
    EventDeliveryReport,
    EventMessageCreate,
    SubscriptionCreate,
    SubscriptionStatusUpdate,
    TopicCreate,
    TopicStatusUpdate,
    TopicUpdate,
)
from app.services.audit import record_audit


def _require_write(request: Request) -> None:
    """写操作统一鉴权：校验内部写入令牌。"""
    if not internal_write_allowed(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "内部写入令牌无效")


# ═══════════════════════════════════════════════════════════
# 事件主题
# ═══════════════════════════════════════════════════════════

class TopicService:
    @staticmethod
    def _to_dict(t: Topic) -> dict:
        return {
            "id": t.id, "name": t.name, "status": t.status, "description": t.description,
            "created_at": t.created_at.isoformat() if t.created_at else "",
            "updated_at": t.updated_at.isoformat() if t.updated_at else "",
        }

    @staticmethod
    async def list_topics(session: AsyncSession, limit: int, offset: int,
                          status_filter: str | None, keyword: str | None) -> dict:
        items = await topic_repo.list_topics(session, limit=limit, offset=offset,
                                             status=status_filter, keyword=keyword)
        total = await topic_repo.count_topics(session, status=status_filter, keyword=keyword)
        return {"total": total, "items": [TopicService._to_dict(t) for t in items]}

    @staticmethod
    async def get_topic(session: AsyncSession, topic_id: str) -> dict:
        topic = await topic_repo.get_topic(session, topic_id)
        if not topic:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "主题不存在")
        return TopicService._to_dict(topic)

    @staticmethod
    async def create_topic(session: AsyncSession, payload: TopicCreate, request: Request) -> dict:
        _require_write(request)
        if await topic_repo.get_topic_by_name(session, payload.name):
            raise HTTPException(status.HTTP_409_CONFLICT, "主题名称已存在")
        topic = Topic(
            id=str(uuid.uuid4()), name=payload.name,
            description=payload.description, status="active",
        )
        topic = await topic_repo.create_topic(session, topic)
        await record_audit(session, "eventbus.topic.created", "internal",
                           f"name={payload.name}", request)
        return TopicService._to_dict(topic)

    @staticmethod
    async def update_topic(session: AsyncSession, topic_id: str, payload: TopicUpdate,
                           request: Request) -> dict:
        _require_write(request)
        topic = await topic_repo.get_topic(session, topic_id)
        if not topic:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "主题不存在")
        if payload.description is not None:
            topic.description = payload.description
        topic = await topic_repo.update_topic(session, topic)
        await record_audit(session, "eventbus.topic.updated", "internal",
                           f"topic_id={topic_id}", request)
        return TopicService._to_dict(topic)

    @staticmethod
    async def update_status(session: AsyncSession, topic_id: str, payload: TopicStatusUpdate,
                            request: Request) -> dict:
        _require_write(request)
        topic = await topic_repo.get_topic(session, topic_id)
        if not topic:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "主题不存在")
        topic.status = payload.status
        topic = await topic_repo.update_topic(session, topic)
        await record_audit(session, "eventbus.topic.status_changed", "internal",
                           f"topic_id={topic_id} status={payload.status}", request)
        return TopicService._to_dict(topic)

    @staticmethod
    async def delete_topic(session: AsyncSession, topic_id: str, request: Request) -> dict:
        _require_write(request)
        topic = await topic_repo.get_topic(session, topic_id)
        if not topic:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "主题不存在")
        await topic_repo.delete_topic(session, topic)
        await record_audit(session, "eventbus.topic.deleted", "internal",
                           f"topic_id={topic_id}", request)
        return {"deleted": True, "id": topic_id}


# ═══════════════════════════════════════════════════════════
# 事件订阅
# ═══════════════════════════════════════════════════════════

class SubscriptionService:
    @staticmethod
    def _to_dict(s: Subscription) -> dict:
        return {
            "id": s.id, "topic_id": s.topic_id, "subscriber_name": s.subscriber_name,
            "endpoint_url": s.endpoint_url, "status": s.status, "description": s.description,
            "created_at": s.created_at.isoformat() if s.created_at else "",
            "updated_at": s.updated_at.isoformat() if s.updated_at else "",
        }

    @staticmethod
    async def list_subscriptions(session: AsyncSession, limit: int, offset: int,
                                 topic_id: str | None, status_filter: str | None) -> dict:
        items = await sub_repo.list_subscriptions(session, limit=limit, offset=offset,
                                                  topic_id=topic_id, status=status_filter)
        total = await sub_repo.count_subscriptions(session, topic_id=topic_id,
                                                   status=status_filter)
        return {"total": total, "items": [SubscriptionService._to_dict(s) for s in items]}

    @staticmethod
    async def get_subscription(session: AsyncSession, sub_id: str) -> dict:
        sub = await sub_repo.get_subscription(session, sub_id)
        if not sub:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "订阅不存在")
        return SubscriptionService._to_dict(sub)

    @staticmethod
    async def create_subscription(session: AsyncSession, topic_id: str,
                                  payload: SubscriptionCreate, request: Request) -> dict:
        _require_write(request)
        topic = await topic_repo.get_topic(session, topic_id)
        if not topic:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "主题不存在")
        if topic.status != "active":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅活跃主题可订阅")
        sub = Subscription(
            id=str(uuid.uuid4()), topic_id=topic.id,
            subscriber_name=payload.subscriber_name, endpoint_url=payload.endpoint_url,
            description=payload.description, status="active",
        )
        sub = await sub_repo.create_subscription(session, sub)
        await record_audit(session, "eventbus.subscription.created", "internal",
                           f"topic={topic.name} sub={payload.subscriber_name}", request)
        return SubscriptionService._to_dict(sub)

    @staticmethod
    async def update_status(session: AsyncSession, sub_id: str,
                            payload: SubscriptionStatusUpdate, request: Request) -> dict:
        _require_write(request)
        sub = await sub_repo.get_subscription(session, sub_id)
        if not sub:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "订阅不存在")
        sub.status = payload.status
        sub = await sub_repo.update_subscription(session, sub)
        await record_audit(session, "eventbus.subscription.status_changed", "internal",
                           f"sub_id={sub_id} status={payload.status}", request)
        return SubscriptionService._to_dict(sub)

    @staticmethod
    async def delete_subscription(session: AsyncSession, sub_id: str, request: Request) -> dict:
        _require_write(request)
        sub = await sub_repo.get_subscription(session, sub_id)
        if not sub:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "订阅不存在")
        await sub_repo.delete_subscription(session, sub)
        await record_audit(session, "eventbus.subscription.deleted", "internal",
                           f"sub_id={sub_id}", request)
        return {"deleted": True, "id": sub_id}


# ═══════════════════════════════════════════════════════════
# 事件消息与投递重试
# ═══════════════════════════════════════════════════════════

class EventMessageService:
    @staticmethod
    def _to_dict(m: EventMessage) -> dict:
        return {
            "id": m.id, "topic_id": m.topic_id, "payload": m.payload,
            "status": m.status, "retry_count": m.retry_count, "max_retries": m.max_retries,
            "last_error": m.last_error,
            "delivered_at": m.delivered_at.isoformat() if m.delivered_at else None,
            "created_at": m.created_at.isoformat() if m.created_at else "",
            "updated_at": m.updated_at.isoformat() if m.updated_at else "",
        }

    @staticmethod
    async def list_messages(session: AsyncSession, limit: int, offset: int,
                            topic_id: str | None, status_filter: str | None) -> dict:
        items = await msg_repo.list_messages(session, limit=limit, offset=offset,
                                             topic_id=topic_id, status=status_filter)
        total = await msg_repo.count_messages(session, topic_id=topic_id, status=status_filter)
        return {"total": total, "items": [EventMessageService._to_dict(m) for m in items]}

    @staticmethod
    async def get_message(session: AsyncSession, msg_id: str) -> dict:
        msg = await msg_repo.get_message(session, msg_id)
        if not msg:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "事件消息不存在")
        return EventMessageService._to_dict(msg)

    @staticmethod
    async def publish(session: AsyncSession, topic_id: str, payload: EventMessageCreate,
                      request: Request) -> dict:
        """发布事件到指定主题，消息初始状态为 pending。"""
        _require_write(request)
        topic = await topic_repo.get_topic(session, topic_id)
        if not topic:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "主题不存在")
        if topic.status != "active":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "主题已暂停，不可发布事件")
        msg = EventMessage(
            id=str(uuid.uuid4()), topic_id=topic.id, payload=payload.payload,
            status="pending", max_retries=payload.max_retries,
        )
        msg = await msg_repo.create_message(session, msg)
        await record_audit(session, "eventbus.event.published", "internal",
                           f"topic={topic.name} msg_id={msg.id}", request)
        return EventMessageService._to_dict(msg)

    @staticmethod
    async def report_delivery(session: AsyncSession, msg_id: str,
                              report: EventDeliveryReport, request: Request) -> dict:
        """投递结果上报：驱动 pending→delivered/failed→dead_letter 状态机。"""
        _require_write(request)
        msg = await msg_repo.get_message(session, msg_id)
        if not msg:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "事件消息不存在")
        if msg.status == "delivered":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "消息已投递，不可重复上报")
        if msg.status == "dead_letter":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "消息已进入死信队列")

        if report.success:
            msg.status = "delivered"
            msg.delivered_at = datetime.now(UTC)
            msg.last_error = ""
        else:
            msg.retry_count += 1
            msg.last_error = report.error
            if msg.retry_count >= msg.max_retries:
                msg.status = "dead_letter"
            else:
                msg.status = "failed"
        msg = await msg_repo.update_message(session, msg)
        await record_audit(session, "eventbus.event.delivery_reported", "internal",
                           f"msg_id={msg_id} status={msg.status}", request)
        return EventMessageService._to_dict(msg)

    @staticmethod
    async def list_retry_queue(session: AsyncSession, topic_id: str | None) -> dict:
        """查询待重试/待投递消息队列。"""
        items = await msg_repo.list_pending_retry(session, topic_id=topic_id, limit=100)
        return {"total": len(items), "items": [EventMessageService._to_dict(m) for m in items]}
