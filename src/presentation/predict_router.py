import logging

from fastapi import APIRouter, HTTPException, Response

from application.predict_service import generate_forecast_pdf

logger = logging.getLogger(__name__)

router = APIRouter(tags=["predict"])


@router.get("/forecast", response_class=Response)
async def get_forecast() -> Response:
    try:
        pdf_bytes = generate_forecast_pdf(horizon_days=7)
        headers = {
            "Content-Disposition": "inline; filename=relatorio_previsao.pdf"
        }
        return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
    except FileNotFoundError as exc:
        logger.exception("CSV não encontrado para previsão", exc_info=exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Falha ao gerar a previsão", exc_info=exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar a previsão") from exc

