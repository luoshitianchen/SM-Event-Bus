"""事件订阅模型：订阅者对某个主题的消费关系。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class Subscription(Base):
    """事件订阅：将主题与订阅者端点绑定，支持暂停/恢复。"""

    __tablename__ = "event_subscriptions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    topic_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subscriber_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    endpoint_url: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
