"""Cron endpoints. Called by Cloud Scheduler with OIDC tokens."""

from __future__ import annotations

from fastapi import APIRouter

from support_service.services.sweep_service import run_media_pass, run_sweep

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/media")
def media_job() -> dict:
    return run_media_pass()


@router.post("/sweep")
def sweep_job() -> dict:
    return run_sweep()
