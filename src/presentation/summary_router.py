from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, Query
from datetime import datetime

from application.dependencies import get_summary_service_dependency
from application.summary_service import SummaryReportService
from infraestructure.pdf_generator import build_summary_report_pdf

logger = logging.getLogger(__name__)

router = APIRouter(tags=["summary"])


@router.get("/summary", response_class=Response)
async def get_summary_report(
    service: SummaryReportService = Depends(get_summary_service_dependency),
    data_inicio: str | None = Query(None, description="Data inicial no formato YYYY-MM-DD"),
    data_fim: str | None = Query(None, description="Data final no formato YYYY-MM-DD"),
) -> Response:
    try:
        # Validação simples de formato quando ambos são fornecidos
        if data_inicio and data_fim:
            try:
                di = datetime.strptime(data_inicio, "%Y-%m-%d").date()
                df = datetime.strptime(data_fim, "%Y-%m-%d").date()
                if di > df:
                    raise HTTPException(status_code=400, detail="data_inicio não pode ser maior que data_fim")
            except ValueError:
                raise HTTPException(status_code=400, detail="Datas devem estar no formato YYYY-MM-DD")

        report_entries, user_open_counts, daily_open_counts = service.generate_cluster_report(
            data_inicio=data_inicio, data_fim=data_fim
        )
        pdf_bytes = build_summary_report_pdf(
            report_entries,
            user_open_counts=user_open_counts,
            daily_open_counts=daily_open_counts,
        )
    except Exception as exc:  # noqa: BLE001 - queremos registrar qualquer falha inesperada
        logger.exception("Falha ao gerar o relatório de resumo", exc_info=exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar o relatório") from exc

    response = Response(content=pdf_bytes, media_type="application/pdf")
    response.headers["Content-Disposition"] = "attachment; filename=summary-report.pdf"
    return response
