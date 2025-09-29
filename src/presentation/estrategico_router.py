from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response

from application.dependencies import get_estrategico_service_dependency
from application.estrategico_service import EstrategicoReportService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["estrategico"])


@router.get("/estrategico", response_class=Response)
async def get_estrategico_report(
    service: EstrategicoReportService = Depends(get_estrategico_service_dependency),
) -> Response:
    try:
        pdf_bytes = service.generate_estrategico_report()
        
    except Exception as exc:  # noqa: BLE001 - queremos registrar qualquer falha inesperada
        logger.exception("Falha ao gerar o relatório estratégico", exc_info=exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar o relatório estratégico") from exc

    response = Response(content=pdf_bytes, media_type="application/pdf")
    response.headers["Content-Disposition"] = "inline; filename=relatorio-estrategico.pdf"
    return response