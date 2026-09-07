"""SM Event Bus —— 企业事件总线：主题、发布/订阅、至少一次投递、重放与死信队列。

依赖共享基础层 app.base 提供安全中间件、国密、审计与指标能力。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field

from app import base

SERVICE = "sm-event-bus"
VERSION = "3.0.0"
NAME = "SM Event Bus"
DESCRIPTION = "企业事件总线：主题管理、事件发布、订阅投递、重放与死信队列"
PORT = 8410


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _init() -> None:
    with base.db_ctx() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS topics (
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT,
                retention_days INTEGER NOT NULL DEFAULT 30, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE, topic TEXT NOT NULL, event_type TEXT NOT NULL,
                payload TEXT NOT NULL, idempotency_key TEXT, created_at TEXT NOT NULL,
                FOREIGN KEY(topic) REFERENCES topics(name)
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, topic TEXT NOT NULL,
                consumer_group TEXT NOT NULL DEFAULT 'default', endpoint TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                id TEXT PRIMARY KEY, subscription_id TEXT NOT NULL, event_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                next_retry_at TEXT, delivered_at TEXT
            );
            CREATE TABLE IF NOT EXISTS dead_letters (
                id TEXT PRIMARY KEY, event_id TEXT NOT NULL, topic TEXT NOT NULL,
                event_type TEXT NOT NULL, payload TEXT NOT NULL, reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_topic ON events(topic, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_deliveries_pending ON deliveries(status, next_retry_at);
            """
        )


app = base.create_app(
    service=SERVICE, name=NAME, description=DESCRIPTION, version=VERSION, port=PORT,
    dependencies=["sm-iam", "sm-audit-log-center"],
    events=["event.published", "event.delivered", "event.dead_lettered", "audit.recorded"],
    overview_fn=lambda _r: {
        "summary": {
            "topics": base.get_db().execute("SELECT COUNT(*) FROM topics").fetchone()[0],
            "events": base.get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "dead_letters": base.get_db().execute("SELECT COUNT(*) FROM dead_letters").fetchone()[0],
        }
    },
    health_checks=lambda: {"database": "ok", "delivery_engine": "ok"},
)
_init()


class TopicIn(BaseModel):
    name: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9._-]+$")
    description: str = Field(default="", max_length=300)
    retention_days: int = Field(default=30, ge=1, le=3650)


class PublishIn(BaseModel):
    topic: str = Field(min_length=2, max_length=80)
    event_type: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=128)


class SubscriptionIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    topic: str = Field(min_length=2, max_length=80)
    consumer_group: str = Field(default="default", min_length=1, max_length=80)
    endpoint: str | None = Field(default=None, max_length=500)


# --------------------------------------------------------------------------- #
# 主题
# --------------------------------------------------------------------------- #
@app.get("/api/events/topics")
def list_topics() -> dict[str, Any]:
    with base.db_ctx() as conn:
        rows = conn.execute("SELECT * FROM topics ORDER BY created_at DESC").fetchall()
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@app.post("/api/events/topics", status_code=status.HTTP_201_CREATED)
def create_topic(payload: TopicIn, request: Request) -> dict[str, Any]:
    base.require_internal_token(request)
    topic_id = str(uuid.uuid4())
    with base.db_ctx() as conn:
        try:
            conn.execute("INSERT INTO topics VALUES (?,?,?,?,?)", (topic_id, payload.name, payload.description, payload.retention_days, _now()))
        except Exception as exc:  # noqa: BLE001 - sqlite IntegrityError
            raise HTTPException(status.HTTP_409_CONFLICT, "主题已存在") from exc
        base.record_audit("topic.created", "internal", f"topic={payload.name}", getattr(request.state, "request_id", ""), getattr(request.state, "trace_id", ""), SERVICE)
    return {"id": topic_id, "name": payload.name}


# --------------------------------------------------------------------------- #
# 发布 / 订阅 / 消费
# --------------------------------------------------------------------------- #
@app.post("/api/events/publish", status_code=status.HTTP_201_CREATED)
def publish(payload: PublishIn, request: Request) -> dict[str, Any]:
    base.require_internal_token(request)
    with base.db_ctx() as conn:
        if not conn.execute("SELECT 1 FROM topics WHERE name=?", (payload.topic,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "主题不存在")
        if payload.idempotency_key:
            existing = conn.execute("SELECT event_id FROM events WHERE topic=? AND idempotency_key=?", (payload.topic, payload.idempotency_key)).fetchone()
            if existing:
                return {"id": existing["event_id"], "duplicate": True, "message": "幂等键重复，已去重"}
        event_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO events (event_id, topic, event_type, payload, idempotency_key, created_at) VALUES (?,?,?,?,?,?)",
            (event_id, payload.topic, payload.event_type, json_dumps(payload.payload), payload.idempotency_key, _now()),
        )
        base.record_audit("event.published", "internal", f"topic={payload.topic} type={payload.event_type}", getattr(request.state, "request_id", ""), getattr(request.state, "trace_id", ""), SERVICE)
    return {"id": event_id, "topic": payload.topic, "duplicate": False}


@app.get("/api/events/subscriptions")
def list_subscriptions() -> dict[str, Any]:
    with base.db_ctx() as conn:
        rows = conn.execute("SELECT * FROM subscriptions ORDER BY created_at DESC").fetchall()
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@app.post("/api/events/subscriptions", status_code=status.HTTP_201_CREATED)
def create_subscription(payload: SubscriptionIn, request: Request) -> dict[str, Any]:
    base.require_internal_token(request)
    sub_id = str(uuid.uuid4())
    with base.db_ctx() as conn:
        if not conn.execute("SELECT 1 FROM topics WHERE name=?", (payload.topic,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "主题不存在")
        conn.execute("INSERT INTO subscriptions VALUES (?,?,?,?,?,?)", (sub_id, payload.name, payload.topic, payload.consumer_group, payload.endpoint, _now()))
    return {"id": sub_id, "topic": payload.topic}


def json_dumps(value: Any) -> str:
    import json as _json
    return _json.dumps(value, ensure_ascii=False, sort_keys=True)


@app.post("/api/events/consume")
def consume(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """订阅拉取：返回待投递事件（至少一次语义），并登记投递记录。"""
    base.require_internal_token(request)
    subscription_id = payload.get("subscription_id", "")
    batch = int(payload.get("batch", 10))
    if batch < 1 or batch > 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "batch 必须在 1-100")
    with base.db_ctx() as conn:
        sub = conn.execute("SELECT * FROM subscriptions WHERE id=?", (subscription_id,)).fetchone()
        if not sub:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "订阅不存在")
        rows = conn.execute(
            """SELECT e.* FROM events e
               WHERE e.topic=? AND NOT EXISTS (
                   SELECT 1 FROM deliveries d WHERE d.event_id=e.event_id AND d.subscription_id=? AND d.status='delivered'
               )
               ORDER BY e.id ASC LIMIT ?""",
            (sub["topic"], subscription_id, batch),
        ).fetchall()
        items = []
        for row in rows:
            delivery_id = str(uuid.uuid4())
            conn.execute("INSERT INTO deliveries (id, subscription_id, event_id, status, attempts, next_retry_at) VALUES (?,?,?,?,?,?)", (delivery_id, subscription_id, row["event_id"], "pending", 0, _now()))
            items.append({"delivery_id": delivery_id, "event_id": row["event_id"], "topic": row["topic"], "event_type": row["event_type"], "payload": __import__("json").loads(row["payload"])})
    return {"subscription_id": subscription_id, "items": items, "count": len(items)}


@app.post("/api/events/ack")
def ack(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    base.require_internal_token(request)
    delivery_id = payload.get("delivery_id", "")
    with base.db_ctx() as conn:
        delivery = conn.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
        if not delivery:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "投递记录不存在")
        conn.execute("UPDATE deliveries SET status='delivered', delivered_at=?, attempts=attempts+1 WHERE id=?", (_now(), delivery_id))
    return {"id": delivery_id, "status": "delivered"}


@app.post("/api/events/nack")
def nack(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """投递失败确认：计入死信（超过最大重试）或安排重试。"""
    base.require_internal_token(request)
    delivery_id = payload.get("delivery_id", "")
    max_attempts = int(payload.get("max_attempts", 5))
    with base.db_ctx() as conn:
        delivery = conn.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
        if not delivery:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "投递记录不存在")
        attempts = delivery["attempts"] + 1
        event = conn.execute("SELECT * FROM events WHERE event_id=?", (delivery["event_id"],)).fetchone()
        if attempts >= max_attempts:
            conn.execute("UPDATE deliveries SET status='dead', attempts=? WHERE id=?", (attempts, delivery_id))
            conn.execute(
                "INSERT INTO dead_letters (id, event_id, topic, event_type, payload, reason, created_at) VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), delivery["event_id"], event["topic"], event["event_type"], event["payload"], f"max attempts {max_attempts} exceeded", _now()),
            )
            return {"id": delivery_id, "status": "dead_lettered"}
        conn.execute("UPDATE deliveries SET status='pending', attempts=? WHERE id=?", (attempts, delivery_id))
    return {"id": delivery_id, "status": "retry_scheduled", "attempts": attempts}


# --------------------------------------------------------------------------- #
# 重放 / 死信
# --------------------------------------------------------------------------- #
@app.post("/api/events/replay/{topic}")
def replay(topic: str, request: Request) -> dict[str, Any]:
    base.require_internal_token(request)
    with base.db_ctx() as conn:
        rows = conn.execute("SELECT event_id FROM events WHERE topic=?", (topic,)).fetchall()
        # 重放：清除已投递状态，使事件可被再次消费
        for row in rows:
            conn.execute("DELETE FROM deliveries WHERE event_id=?", (row["event_id"],))
    return {"topic": topic, "replayed": len(rows), "message": "已重置投递状态，可重新消费"}


@app.get("/api/events/dead-letters")
def list_dead_letters() -> dict[str, Any]:
    with base.db_ctx() as conn:
        rows = conn.execute("SELECT * FROM dead_letters ORDER BY created_at DESC LIMIT 100").fetchall()
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@app.post("/api/events/dead-letters/{dead_id}/retry")
def retry_dead_letter(dead_id: str, request: Request) -> dict[str, Any]:
    base.require_internal_token(request)
    with base.db_ctx() as conn:
        dead = conn.execute("SELECT * FROM dead_letters WHERE id=?", (dead_id,)).fetchone()
        if not dead:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "死信记录不存在")
        # 事件仍保留在 events 表；重置其投递状态使其可被重新消费
        conn.execute("DELETE FROM deliveries WHERE event_id=?", (dead["event_id"],))
        conn.execute("DELETE FROM dead_letters WHERE id=?", (dead_id,))
    return {"event_id": dead["event_id"], "message": "已重新入队"}


@app.get("/api/events/stats")
def stats() -> dict[str, Any]:
    with base.db_ctx() as conn:
        def _count(sql: str) -> int:
            return conn.execute(sql).fetchone()[0]
        return {
            "topics": _count("SELECT COUNT(*) FROM topics"),
            "events": _count("SELECT COUNT(*) FROM events"),
            "subscriptions": _count("SELECT COUNT(*) FROM subscriptions"),
            "delivered": _count("SELECT COUNT(*) FROM deliveries WHERE status='delivered'"),
            "pending": _count("SELECT COUNT(*) FROM deliveries WHERE status='pending'"),
            "dead_letters": _count("SELECT COUNT(*) FROM dead_letters"),
        }