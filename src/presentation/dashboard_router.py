from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response

from application.dependencies import get_dashboard_service_dependency
from application.dashboard_service import DashboardReportService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=Response)
async def get_dashboard_report(
    service: DashboardReportService = Depends(get_dashboard_service_dependency),
) -> Response:
    try:
        pdf_bytes = service.generate_dashboard_report()
        
    except Exception as exc:  # noqa: BLE001 - queremos registrar qualquer falha inesperada
        logger.exception("Falha ao gerar o dashboard", exc_info=exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar o dashboard") from exc

    response = Response(content=pdf_bytes, media_type="application/pdf")
    response.headers["Content-Disposition"] = 'inline; filename=\"dashboard-causas-raizes.pdf\"'
    return response