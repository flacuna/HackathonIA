from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response

from application.dependencies import get_summary_service_dependency
from application.summary_service import SummaryReportService
from infraestructure.pdf_generator import build_summary_report_pdf

logger = logging.getLogger(__name__)

router = APIRouter(tags=["summary"])


@router.get("/summary", response_class=Response)
async def get_summary_report(
    service: SummaryReportService = Depends(get_summary_service_dependency),
) -> Response:
    try:
        report_entries = service.generate_cluster_report()
        pdf_bytes = build_summary_report_pdf(report_entries)
    except Exception as exc:  # noqa: BLE001 - queremos registrar qualquer falha inesperada
        logger.exception("Falha ao gerar o relatório de resumo", exc_info=exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar o relatório") from exc

    response = Response(content=pdf_bytes, media_type="application/pdf")
    response.headers["Content-Disposition"] = "attachment; filename=summary-report.pdf"
    return response
