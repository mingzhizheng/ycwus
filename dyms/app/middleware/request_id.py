import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            user_id=getattr(request.state, "user_id", None),
            facility_id=request.query_params.get("facility_id"),
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = trace_id
        return response
