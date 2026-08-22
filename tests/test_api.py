from fastapi.testclient import TestClient
from app.main import app

def test_health_security():
 with TestClient(app) as c:
  r=c.get('/health'); assert r.status_code==200; assert r.headers['X-Frame-Options']=='DENY'

def test_lifecycle():
 with TestClient(app) as c:
  assert c.post('/api/items',json={'name':'测试资源'}).status_code==201
  assert c.get('/api/overview').json()['total']==1

def test_crypto_metrics():
 with TestClient(app) as c:
  assert c.get('/api/crypto/status').json()['sm3']=='enabled'; assert c.get('/api/ops/metrics').status_code==200
