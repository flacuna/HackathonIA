from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Dict, Any, List
import os

from infraestructure.pdf_estrategico import build_relatorio_estrategico_pdf


class JiraRepository(Protocol):
    def get_rows_by_ids(self, ids: List[str], date_range: Optional[tuple[str, str]] = None) -> List[Dict[str, Any]]: ...


@dataclass(frozen=True)
class EstrategicoServiceSettings:
    csv_path: str


class EstrategicoReportService:
    def __init__(
        self,
        settings: EstrategicoServiceSettings,
        jira_repo: Optional[JiraRepository] = None,
    ) -> None:
        self._settings = settings
        self._jira_repo = jira_repo

    def generate_estrategico_report(self) -> bytes:
        """Gera relatório estratégico em PDF"""
        try:
            pdf_bytes = build_relatorio_estrategico_pdf(self._settings.csv_path)
            return pdf_bytes
        except Exception as exc:
            raise RuntimeError(f"Erro ao gerar relatório estratégico: {exc}") from exc