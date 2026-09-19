"""事件总线业务域深化测试：主题 / 订阅 / 事件投递与重试。"""
from __future__ import annotations

H = {"X-Internal-Token": "test-internal-key-12345"}


# ═══════════════════════════════════════════════════════════
# 事件主题
# ═══════════════════════════════════════════════════════════

class TestTopics:
    async def test_create_topic_success(self, client):
        resp = await client.post("/api/eventbus/topics", json={
            "name": "order.created", "description": "订单创建事件",
        }, headers=H)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "order.created"
        assert data["status"] == "active"

    async def test_create_topic_duplicate_name(self, client):
        await client.post("/api/eventbus/topics", json={"name": "dup.topic"}, headers=H)
        resp = await client.post("/api/eventbus/topics", json={"name": "dup.topic"}, headers=H)
        assert resp.status_code == 409

    async def test_list_topics_read_without_token(self, client):
        resp = await client.get("/api/eventbus/topics")
        assert resp.status_code == 200
        assert "total" in resp.json()

    async def test_create_topic_requires_token(self, client):
        resp = await client.post("/api/eventbus/topics", json={"name": "no.token.topic"})
        assert resp.status_code == 403

    async def test_get_topic_by_id(self, client):
        create = await client.post("/api/eventbus/topics", json={"name": "get.topic"}, headers=H)
        tid = create.json()["id"]
        resp = await client.get(f"/api/eventbus/topics/{tid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == tid

    async def test_get_topic_not_found(self, client):
        resp = await client.get("/api/eventbus/topics/nonexistent")
        assert resp.status_code == 404

    async def test_pause_topic_rejects_publish(self, client):
        create = await client.post("/api/eventbus/topics", json={"name": "pausable.topic"}, headers=H)
        tid = create.json()["id"]
        await client.patch(f"/api/eventbus/topics/{tid}/status",
                           json={"status": "paused"}, headers=H)
        resp = await client.post(f"/api/eventbus/topics/{tid}/events",
                                 json={"payload": "{}"}, headers=H)
        assert resp.status_code == 400

    async def test_update_topic(self, client):
        create = await client.post("/api/eventbus/topics", json={"name": "upd.topic"}, headers=H)
        tid = create.json()["id"]
        resp = await client.patch(f"/api/eventbus/topics/{tid}",
                                   json={"description": "更新描述"}, headers=H)
        assert resp.status_code == 200
        assert resp.json()["description"] == "更新描述"

    async def test_delete_topic(self, client):
        create = await client.post("/api/eventbus/topics", json={"name": "del.topic"}, headers=H)
        tid = create.json()["id"]
        resp = await client.delete(f"/api/eventbus/topics/{tid}", headers=H)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


# ═══════════════════════════════════════════════════════════
# 事件订阅
# ═══════════════════════════════════════════════════════════

class TestSubscriptions:
    async def _make_topic(self, client, name="sub.topic") -> str:
        create = await client.post("/api/eventbus/topics", json={"name": name}, headers=H)
        return create.json()["id"]

    async def test_create_subscription_success(self, client):
        tid = await self._make_topic(client)
        resp = await client.post(f"/api/eventbus/topics/{tid}/subscriptions", json={
            "subscriber_name": "order-service", "endpoint_url": "http://order:8000/hook",
        }, headers=H)
        assert resp.status_code == 201
        assert resp.json()["subscriber_name"] == "order-service"
        assert resp.json()["status"] == "active"

    async def test_create_subscription_nonexistent_topic(self, client):
        resp = await client.post("/api/eventbus/topics/nonexistent/subscriptions",
                                 json={"subscriber_name": "svc", "endpoint_url": "http://x"},
                                 headers=H)
        assert resp.status_code == 404

    async def test_list_subscriptions_read_without_token(self, client):
        tid = await self._make_topic(client, "list.sub.topic")
        await client.post(f"/api/eventbus/topics/{tid}/subscriptions",
                          json={"subscriber_name": "svc", "endpoint_url": "http://x"}, headers=H)
        resp = await client.get(f"/api/eventbus/topics/{tid}/subscriptions")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    async def test_pause_subscription(self, client):
        tid = await self._make_topic(client, "pause.sub.topic")
        create = await client.post(f"/api/eventbus/topics/{tid}/subscriptions",
                                    json={"subscriber_name": "svc", "endpoint_url": "http://x"},
                                    headers=H)
        sid = create.json()["id"]
        resp = await client.patch(f"/api/eventbus/topics/subscriptions/{sid}/status",
                                   json={"status": "paused"}, headers=H)
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    async def test_delete_subscription(self, client):
        tid = await self._make_topic(client, "del.sub.topic")
        create = await client.post(f"/api/eventbus/topics/{tid}/subscriptions",
                                    json={"subscriber_name": "svc", "endpoint_url": "http://x"},
                                    headers=H)
        sid = create.json()["id"]
        resp = await client.delete(f"/api/eventbus/topics/subscriptions/{sid}", headers=H)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


# ═══════════════════════════════════════════════════════════
# 事件投递与重试状态机
# ═══════════════════════════════════════════════════════════

class TestEventDelivery:
    async def _make_topic(self, client, name="event.topic") -> str:
        create = await client.post("/api/eventbus/topics", json={"name": name}, headers=H)
        return create.json()["id"]

    async def test_publish_event_success(self, client):
        tid = await self._make_topic(client)
        resp = await client.post(f"/api/eventbus/topics/{tid}/events",
                                  json={"payload": '{"order_id":123}'}, headers=H)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["retry_count"] == 0

    async def test_list_events_read_without_token(self, client):
        tid = await self._make_topic(client, "list.event.topic")
        resp = await client.get(f"/api/eventbus/topics/{tid}/events")
        assert resp.status_code == 200
        assert "total" in resp.json()

    async def test_deliver_success(self, client):
        tid = await self._make_topic(client, "ok.deliver.topic")
        pub = await client.post(f"/api/eventbus/topics/{tid}/events",
                                 json={"payload": "{}"}, headers=H)
        mid = pub.json()["id"]
        resp = await client.post(f"/api/eventbus/topics/events/{mid}/delivery",
                                 json={"success": True}, headers=H)
        assert resp.status_code == 200
        assert resp.json()["status"] == "delivered"
        assert resp.json()["delivered_at"] is not None

    async def test_deliver_failure_retries_then_dead_letter(self, client):
        tid = await self._make_topic(client, "retry.topic")
        pub = await client.post(f"/api/eventbus/topics/{tid}/events",
                                 json={"payload": "{}", "max_retries": 2}, headers=H)
        mid = pub.json()["id"]
        # 第一次失败
        r1 = await client.post(f"/api/eventbus/topics/events/{mid}/delivery",
                                json={"success": False, "error": "超时"}, headers=H)
        assert r1.json()["status"] == "failed"
        assert r1.json()["retry_count"] == 1
        # 第二次失败 → 超过 max_retries → 死信
        r2 = await client.post(f"/api/eventbus/topics/events/{mid}/delivery",
                                json={"success": False, "error": "再次超时"}, headers=H)
        assert r2.json()["status"] == "dead_letter"
        assert r2.json()["retry_count"] == 2

    async def test_deliver_dead_letter_rejected(self, client):
        tid = await self._make_topic(client, "dead.topic")
        pub = await client.post(f"/api/eventbus/topics/{tid}/events",
                                 json={"payload": "{}", "max_retries": 1}, headers=H)
        mid = pub.json()["id"]
        await client.post(f"/api/eventbus/topics/events/{mid}/delivery",
                          json={"success": False, "error": "e1"}, headers=H)
        await client.post(f"/api/eventbus/topics/events/{mid}/delivery",
                          json={"success": False, "error": "e2"}, headers=H)
        # 死信后再上报应被拒绝
        resp = await client.post(f"/api/eventbus/topics/events/{mid}/delivery",
                                  json={"success": True}, headers=H)
        assert resp.status_code == 400

    async def test_delivered_event_rejected(self, client):
        tid = await self._make_topic(client, "once.topic")
        pub = await client.post(f"/api/eventbus/topics/{tid}/events",
                                 json={"payload": "{}"}, headers=H)
        mid = pub.json()["id"]
        await client.post(f"/api/eventbus/topics/events/{mid}/delivery",
                          json={"success": True}, headers=H)
        resp = await client.post(f"/api/eventbus/topics/events/{mid}/delivery",
                                  json={"success": True}, headers=H)
        assert resp.status_code == 400

    async def test_retry_queue_lists_pending(self, client):
        tid = await self._make_topic(client, "queue.topic")
        await client.post(f"/api/eventbus/topics/{tid}/events",
                          json={"payload": "{}"}, headers=H)
        resp = await client.get(f"/api/eventbus/retry-queue?topic_id={tid}")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    async def test_publish_event_requires_token(self, client):
        tid = await self._make_topic(client, "no.token.pub.topic")
        resp = await client.post(f"/api/eventbus/topics/{tid}/events",
                                  json={"payload": "{}"})
        assert resp.status_code == 403
