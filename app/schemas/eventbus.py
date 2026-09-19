"""事件总线 Pydantic 模型：主题 / 订阅 / 事件消息。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════
# 事件主题
# ═══════════════════════════════════════════════════════════

class TopicCreate(BaseModel):
    name: str = Field(min_length=2, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")
    description: str = Field(default="", max_length=2048)


class TopicUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=2048)


class TopicStatusUpdate(BaseModel):
    status: Literal["active", "paused"]


# ═══════════════════════════════════════════════════════════
# 事件订阅
# ═══════════════════════════════════════════════════════════

class SubscriptionCreate(BaseModel):
    subscriber_name: str = Field(min_length=2, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")
    endpoint_url: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=2048)


class SubscriptionStatusUpdate(BaseModel):
    status: Literal["active", "paused"]


# ═══════════════════════════════════════════════════════════
# 事件消息
# ═══════════════════════════════════════════════════════════

class EventMessageCreate(BaseModel):
    payload: str = Field(min_length=1, max_length=65536)
    max_retries: int = Field(default=3, ge=0, le=100)


class EventDeliveryReport(BaseModel):
    success: bool
    error: str = Field(default="", max_length=2048)
