import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api import router
from app.auth import router as auth_router
from app.modules.vehicle_resolution.routes import router as vehicle_resolution_router
from app.modules.vehicle_data.routes import router as vehicle_data_router
from app.modules.diagnostic_ai.routes import router as diagnostic_ai_router
from app.modules.diagnostic_data.routes import router as diagnostic_data_router
from app.workspace import router as workspace_router
from app.core.config import settings
from app.core.logging import configure_logging, logger

configure_logging()

class PayloadTooLarge(Exception):pass

class PayloadLimitMiddleware:
    def __init__(self,app,limit:int):self.app=app;self.limit=limit
    async def __call__(self,scope,receive,send):
        if scope.get("type")!="http":return await self.app(scope,receive,send)
        headers=dict(scope.get("headers",[]))
        try:declared_length=int(headers.get(b"content-length",b"0"))
        except ValueError:declared_length=0
        if declared_length>self.limit:
            return await JSONResponse(status_code=413,content={"detail":"Requête trop volumineuse"})(scope,receive,send)
        total=0
        async def limited_receive():
            nonlocal total
            message=await receive()
            total+=len(message.get("body",b""))
            if total>self.limit:raise PayloadTooLarge()
            return message
        try:return await self.app(scope,limited_receive,send)
        except PayloadTooLarge:
            return await JSONResponse(status_code=413,content={"detail":"Requête trop volumineuse"})(scope,receive,send)

app=FastAPI(title="DiagPilot API",version="0.1.0",description="MVP fictif d’assistance au diagnostic automobile. Lecture seule.")
app.add_middleware(PayloadLimitMiddleware,limit=settings.max_request_bytes)
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(",")],allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE"],allow_headers=["Authorization","Content-Type"])
app.include_router(auth_router)
app.include_router(router)
app.include_router(vehicle_resolution_router)
app.include_router(vehicle_data_router)
app.include_router(diagnostic_ai_router)
app.include_router(diagnostic_data_router)
app.include_router(workspace_router)
@app.middleware("http")
async def request_context(request:Request,call_next):
    request_id=request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id=request_id
    response=await call_next(request)
    response.headers["X-Request-ID"]=request_id
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="no-referrer"
    return response
@app.exception_handler(Exception)
async def unexpected(request:Request,exc:Exception):
    request_id=getattr(request.state,"request_id",str(uuid.uuid4()))
    logger.exception("unhandled_error",path=request.url.path,error_type=type(exc).__name__,request_id=request_id)
    return JSONResponse(status_code=500,content={"detail":"Erreur interne.","request_id":request_id},headers={"X-Request-ID":request_id})
