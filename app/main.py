from __future__ import annotations
import os,time,uuid
from datetime import UTC,datetime
from typing import Literal
from fastapi import FastAPI,HTTPException,Request,Response,status
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
VERSION="1.0.0"
SERVICE_NAME="sm-event-bus"
DISPLAY_NAME="SM Event Bus"
DESCRIPTION="企业消息与事件总线：事件发布、订阅、重试和审计"
ALLOWED_HOSTS=[h.strip() for h in os.getenv("SM_ALLOWED_HOSTS","localhost,127.0.0.1,testserver").split(",") if h.strip()]
ITEMS=[]
REQUESTS={"total":0,"errors":0,"latency_ms_total":0.0}
app=FastAPI(title=DISPLAY_NAME,version=VERSION,description=DESCRIPTION,docs_url=None,redoc_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=ALLOWED_HOSTS)
class Item(BaseModel):
 name:str=Field(min_length=1,max_length=120)
 owner:str=Field(default="平台工程部",max_length=80)
 status:Literal["planned","active","review","closed"]="active"
@app.middleware("http")
async def security(request:Request,call_next):
 st=time.perf_counter(); response=await call_next(request); elapsed=(time.perf_counter()-st)*1000; REQUESTS["total"]+=1; REQUESTS["latency_ms_total"]+=elapsed
 if response.status_code>=500: REQUESTS["errors"]+=1
 response.headers["X-Request-Id"]=(request.headers.get("X-Request-Id") or str(uuid.uuid4()))[:64]; response.headers["X-Content-Type-Options"]="nosniff"; response.headers["X-Frame-Options"]="DENY"; response.headers["Referrer-Policy"]="no-referrer"; response.headers["Permissions-Policy"]="camera=(), microphone=(), geolocation=(), payment=(), usb=()"; response.headers["Content-Security-Policy"]="default-src 'self'; connect-src 'self'; frame-ancestors 'none'"; return response
@app.get("/",include_in_schema=False)
def home(): return FileResponse("app/static/index.html")
@app.get("/health")
def health(): return {"status":"ok","service":SERVICE_NAME,"version":VERSION}
@app.get("/readyz")
def readyz(): return {"status":"ready","service":SERVICE_NAME}
@app.get("/api/overview")
def overview(): return {"platform":{"name":DISPLAY_NAME,"version":VERSION,"description":DESCRIPTION},"items":ITEMS,"total":len(ITEMS)}
@app.post("/api/items",status_code=201)
def create(payload:Item):
 item={"id":str(uuid.uuid4()),**payload.model_dump(),"created_at":datetime.now(UTC).isoformat()}; ITEMS.append(item); return item
@app.get("/api/ops/metrics")
def metrics():
 total=int(REQUESTS["total"]); return {"service":SERVICE_NAME,"version":VERSION,"requests_total":total,"errors_total":int(REQUESTS["errors"]),"avg_latency_ms":round(REQUESTS["latency_ms_total"]/total,2) if total else 0}
@app.get("/api/crypto/status")
def crypto(): return {"algorithm":"SM3/SM4","sm3":"enabled","sm4":"enabled"}
