from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.logging_config import setup_logging
from app.redis_client import init_redis, close_redis
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.rate_limit import limiter
from app.auth.router import router as auth_router
from app.asns.router import router as asn_router
from app.appointments.router import router as appointment_router
from app.checkin.router import router as checkin_router
from app.dock.router import router as dock_router
from app.evidence.router import router as evidence_router
from app.billing.router import router as billing_router
from app.calendar.router import router as calendar_router
from app.reports.router import router as reports_router
from app.websocket.manager import router as ws_router
from app.tasks.scheduler import register_tasks, shutdown_tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_redis()
    register_tasks()
    yield
    shutdown_tasks()
    await close_redis()


app = FastAPI(
    title="DYMS",
    description="Dock & Yard Management System V2.2",
    version="2.2.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Routers
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(asn_router, prefix="/api/asns", tags=["ASN"])
app.include_router(appointment_router, prefix="/api/appointments", tags=["Appointments"])
app.include_router(checkin_router, prefix="/api/checkin", tags=["Check-in"])
app.include_router(dock_router, prefix="/api/dock", tags=["Dock"])
app.include_router(evidence_router, prefix="/api/evidence", tags=["Evidence"])
app.include_router(billing_router, prefix="/api/billing", tags=["Billing"])
app.include_router(calendar_router, prefix="/api/calendar", tags=["Calendar"])
app.include_router(reports_router, prefix="/api/reports", tags=["Reports"])
app.include_router(ws_router, tags=["WebSocket"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.2.0"}
