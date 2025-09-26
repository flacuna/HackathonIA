from __future__ import annotations

from fastapi import APIRouter, Depends

from application.dependencies import get_summary_settings
from application.health_service import HealthService

router = APIRouter(tags=["health"])


@router.get("/health/chroma")
async def chroma_health():
    settings = get_summary_settings()
    service = HealthService(settings)
    return service.check_chroma().__dict__
