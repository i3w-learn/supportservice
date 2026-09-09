"""Cloud Run entrypoint.

Module routers get mounted here as they are built (§3, §9).
"""

import os

from fastapi import FastAPI

from support_service.admin_api.routes import router as admin_router
from support_service.channel import webhook_router
from support_service.jobs.routes import router as jobs_router

# Interactive docs are a local-dev convenience. In production this is an
# admin-only service behind Firebase Auth — it should not advertise its
# surface. Cloud Run sets ENV=production.
_IS_DEV = os.environ.get("ENV", "development") != "production"

app = FastAPI(
    title="support-service",
    description="WhatsApp support and ticketing for i3w.ai products.",
    version="0.1.0",
    docs_url="/docs" if _IS_DEV else None,
    redoc_url="/redoc" if _IS_DEV else None,
    openapi_url="/openapi.json" if _IS_DEV else None,
)

app.include_router(webhook_router)
app.include_router(admin_router)
app.include_router(jobs_router)


@app.get("/healthz", tags=["ops"], summary="Liveness probe")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
