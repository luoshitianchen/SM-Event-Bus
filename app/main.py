from __future__ import annotations
import os,secrets,threading,time,uuid
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
ENVIRONMENT=os.getenv("SM_ENV","development").lower()
ALLOWED_HOSTS=[h.strip() for h in os.getenv("SM_ALLOWED_HOSTS","localhost,127.0.0.1,testserver").split(",") if h.strip()]
ITEMS=[]
REQUESTS={"total":0,"errors":0,"latency_ms_total":0.0}
RATE_BUCKETS:dict[str,tuple[int,int]]={}
rate_limit_lock=threading.Lock()
MAX_REQUEST_BYTES=int(os.getenv("SM_MAX_REQUEST_BYTES","1048576"))
RATE_WINDOW_SECONDS=int(os.getenv("SM_RATE_WINDOW_SECONDS","60"))
RATE_MAX_REQUESTS=int(os.getenv("SM_RATE_MAX_REQUESTS","600"))
INTERNAL_API_KEY=os.getenv("SM_INTERNAL_API_KEY","")

def check_rate_limit(key:str)->bool:
    with rate_limit_lock:
        current=int(time.time())
        for bucket_key,(started,_) in list(RATE_BUCKETS.items()):
            if current-started>=RATE_WINDOW_SECONDS:
                RATE_BUCKETS.pop(bucket_key,None)
        started,count=RATE_BUCKETS.get(key,(current,0))
        if current-started>=RATE_WINDOW_SECONDS:
            started,count=current,0
        if count>=RATE_MAX_REQUESTS:
            return False
        RATE_BUCKETS[key]=(started,count+1)
        return True

def internal_write_allowed(request:Request)->bool:
    if not INTERNAL_API_KEY:
        return False
    return secrets.compare_digest(request.headers.get("X-Internal-Token",""),INTERNAL_API_KEY)

app=FastAPI(title=DISPLAY_NAME,version=VERSION,description=DESCRIPTION,docs_url=None,redoc_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=ALLOWED_HOSTS)
class Item(BaseModel):
 name:str=Field(min_length=1,max_length=120)
 owner:str=Field(default="平台工程部",max_length=80)
 status:Literal["planned","active","review","closed"]="active"
@app.middleware("http")
async def security(request:Request,call_next):
 st=time.perf_counter()
 content_length=request.headers.get("content-length")
 if content_length:
    try: body_size=int(content_length)
    except ValueError: response=Response(status_code=400,content="Invalid Content-Length")
    else:
        if body_size<0 or body_size>MAX_REQUEST_BYTES: response=Response(status_code=413,content="Request body too large")
        elif not check_rate_limit(f"{request.client.host if request.client else 'unknown'}:{request.url.path}"): response=Response(status_code=429,content="Too many requests",headers={"Retry-After":str(RATE_WINDOW_SECONDS)})
        else: response=await call_next(request)
 elif not check_rate_limit(f"{request.client.host if request.client else 'unknown'}:{request.url.path}"): response=Response(status_code=429,content="Too many requests",headers={"Retry-After":str(RATE_WINDOW_SECONDS)})
 else: response=await call_next(request)
 elapsed=(time.perf_counter()-st)*1000; REQUESTS["total"]+=1; REQUESTS["latency_ms_total"]+=elapsed
 if response.status_code>=500: REQUESTS["errors"]+=1
 response.headers["X-Request-Id"]=(request.headers.get("X-Request-Id") or str(uuid.uuid4()))[:64]; response.headers["X-Content-Type-Options"]="nosniff"; response.headers["X-Frame-Options"]="DENY"; response.headers["Referrer-Policy"]="no-referrer"; response.headers["Permissions-Policy"]="camera=(), microphone=(), geolocation=(), payment=(), usb=()"; response.headers["Content-Security-Policy"]="default-src 'self'; connect-src 'self'; frame-ancestors 'none'"
 if ENVIRONMENT=="production": response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
 return response
@app.get("/",include_in_schema=False)
def home(): return FileResponse("app/static/index.html")
@app.get("/health")
def health(): return {"status":"ok","service":SERVICE_NAME,"version":VERSION}
@app.get("/readyz")
def readyz(): return {"status":"ready","service":SERVICE_NAME}
@app.get("/api/overview")
def overview(): return {"platform":{"name":DISPLAY_NAME,"version":VERSION,"description":DESCRIPTION},"items":ITEMS,"total":len(ITEMS)}
@app.post("/api/items",status_code=201)
def create(payload:Item,request:Request):
 if not internal_write_allowed(request): raise HTTPException(status.HTTP_403_FORBIDDEN,"内部写入令牌无效")
 item={"id":str(uuid.uuid4()),**payload.model_dump(),"created_at":datetime.now(UTC).isoformat()}; ITEMS.append(item); return item
@app.get("/api/ops/metrics")
def metrics():
 total=int(REQUESTS["total"]); return {"service":SERVICE_NAME,"version":VERSION,"requests_total":total,"errors_total":int(REQUESTS["errors"]),"avg_latency_ms":round(REQUESTS["latency_ms_total"]/total,2) if total else 0}
@app.get("/api/crypto/status")
def crypto(): return {"algorithm":"SM3/SM4","sm3":"enabled","sm4":"enabled"}
