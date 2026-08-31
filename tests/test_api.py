"""SM Event Bus 领域测试：主题/发布/订阅/消费/ACK/NACK/重放/死信。"""

import pytest
from fastapi.testclient import TestClient

from app import base
from app.main import VERSION, app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(base, "internal_api_key", lambda: "TEST")
    base.reset_state()
    from app.main import _init as init_db
    init_db()
    with TestClient(app) as c:
        c.headers["X-Internal-Token"] = "TEST"
        yield c


def _topic(client, name="orders"):
    return client.post("/api/events/topics", headers={"X-Internal-Token": "TEST"}, json={"name": name, "description": "订单事件"}).json()["id"]


def test_health_and_security_headers(client):
    r = client.get("/health", headers={"X-Request-Id": "suite-test"})
    assert r.status_code == 200
    assert r.headers["X-Request-Id"] == "suite-test"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.json()["version"] == VERSION


def test_topic_lifecycle(client):
    _topic(client)
    dup = client.post("/api/events/topics", headers={"X-Internal-Token": "TEST"}, json={"name": "orders"})
    assert dup.status_code == 409
    assert client.get("/api/events/topics").json()["total"] == 1


def test_publish_and_idempotency(client):
    _topic(client)
    created = client.post("/api/events/publish", headers={"X-Internal-Token": "TEST"}, json={"topic": "orders", "event_type": "order.created", "payload": {"order_id": "A1"}, "idempotency_key": "k-1"})
    assert created.status_code == 201
    duplicate = client.post("/api/events/publish", headers={"X-Internal-Token": "TEST"}, json={"topic": "orders", "event_type": "order.created", "payload": {"order_id": "A1"}, "idempotency_key": "k-1"})
    assert duplicate.json()["duplicate"] is True
    assert client.get("/api/events/stats").json()["events"] == 1


def test_consume_ack_and_nack_to_dead_letter(client):
    _topic(client)
    client.post("/api/events/publish", headers={"X-Internal-Token": "TEST"}, json={"topic": "orders", "event_type": "order.created", "payload": {"id": 1}})
    sub = client.post("/api/events/subscriptions", headers={"X-Internal-Token": "TEST"}, json={"name": "billing", "topic": "orders"}).json()["id"]
    batch = client.post("/api/events/consume", headers={"X-Internal-Token": "TEST"}, json={"subscription_id": sub}).json()
    assert batch["count"] == 1
    delivery_id = batch["items"][0]["delivery_id"]
    assert client.post("/api/events/ack", headers={"X-Internal-Token": "TEST"}, json={"delivery_id": delivery_id}).json()["status"] == "delivered"
    # 已投递不再重复消费
    assert client.post("/api/events/consume", headers={"X-Internal-Token": "TEST"}, json={"subscription_id": sub}).json()["count"] == 0


def test_nack_dead_letter_and_retry(client):
    _topic(client)
    client.post("/api/events/publish", headers={"X-Internal-Token": "TEST"}, json={"topic": "orders", "event_type": "order.created", "payload": {"id": 2}})
    sub = client.post("/api/events/subscriptions", headers={"X-Internal-Token": "TEST"}, json={"name": "worker", "topic": "orders"}).json()["id"]
    batch = client.post("/api/events/consume", headers={"X-Internal-Token": "TEST"}, json={"subscription_id": sub}).json()
    delivery_id = batch["items"][0]["delivery_id"]
    result = client.post("/api/events/nack", headers={"X-Internal-Token": "TEST"}, json={"delivery_id": delivery_id, "max_attempts": 1})
    assert result.json()["status"] == "dead_lettered"
    assert client.get("/api/events/dead-letters").json()["total"] == 1
    dead_id = client.get("/api/events/dead-letters").json()["items"][0]["id"]
    retry = client.post(f"/api/events/dead-letters/{dead_id}/retry", headers={"X-Internal-Token": "TEST"})
    assert retry.status_code == 200
    assert client.get("/api/events/dead-letters").json()["total"] == 0


def test_replay(client):
    _topic(client)
    client.post("/api/events/publish", headers={"X-Internal-Token": "TEST"}, json={"topic": "orders", "event_type": "order.created", "payload": {"id": 3}})
    sub = client.post("/api/events/subscriptions", headers={"X-Internal-Token": "TEST"}, json={"name": "auditor", "topic": "orders"}).json()["id"]
    client.post("/api/events/consume", headers={"X-Internal-Token": "TEST"}, json={"subscription_id": sub})
    replay = client.post("/api/events/replay/orders", headers={"X-Internal-Token": "TEST"})
    assert replay.json()["replayed"] == 1
    assert client.post("/api/events/consume", headers={"X-Internal-Token": "TEST"}, json={"subscription_id": sub}).json()["count"] == 1


def test_write_requires_auth(client):
    del client.headers["X-Internal-Token"]
    assert client.post("/api/events/topics", json={"name": "x"}).status_code == 401


def test_manifest_and_baseline(client):
    manifest = client.get("/api/integration/manifest").json()
    assert manifest["version"] == VERSION
    assert "sm-audit-log-center" in manifest["dependencies"]
    controls = client.get("/api/security/baseline").json()["controls"]
    assert controls["sm4_integrity_mac"] is True


def test_crypto_tamper_detection(client):
    enc = client.post("/api/crypto/encrypt", json={"value": "secret"}).json()["ciphertext"]
    assert client.post("/api/crypto/decrypt", json={"value": enc}).json()["plaintext"] == "secret"
    tampered = enc[:-2] + ("00" if not enc.endswith("00") else "11")
    assert client.post("/api/crypto/decrypt", json={"value": tampered}).status_code == 400
