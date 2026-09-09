# backend/src/support_service/jobs/routes.py
"""Cron endpoints. Called by Cloud Scheduler with OIDC tokens."""

from fastapi import APIRouter

from support_service.jobs.media_pass import run_media_pass
from support_service.jobs.sweep import run_sweep

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/media")
def media_job() -> dict:
    return run_media_pass()


@router.post("/sweep")
def sweep_job() -> dict:
    return run_sweep()
