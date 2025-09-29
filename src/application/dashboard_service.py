from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Dict, Any, List, Tuple
from collections import Counter

from infraestructure.dashboard import build_dashboard_pdf


class JiraRepository(Protocol):
    def get_rows_by_ids(self, ids: List[str], date_range: Optional[tuple[str, str]] = None) -> List[Dict[str, Any]]: ...


@dataclass(frozen=True)
class DashboardServiceSettings:
    csv_path: str


class DashboardReportService:
    def __init__(
        self,
        settings: DashboardServiceSettings,
        jira_repo: Optional[JiraRepository] = None,
    ) -> None:
        self._settings = settings
        self._jira_repo = jira_repo

    def _ofuscar_nomes_usuarios(self, user_counts: List[Tuple[str, int]]) -> List[Tuple[str, int]]:
        """Ofusca nomes de usuários para pseudonimização no relatório"""
        alias_map: Dict[str, str] = {}
        masked_counts: List[Tuple[str, int]] = []
        seq = 1
        for real_name, count in user_counts:
            key = real_name.strip()
            if key not in alias_map:
                alias_map[key] = f"Usuário #{seq}"
                seq += 1
            masked_counts.append((alias_map[key], count))
        return masked_counts

    def generate_dashboard_report(self) -> bytes:
        """Gera dashboard de causas raízes e KPIs executivos em PDF"""
        try:
            pdf_bytes = build_dashboard_pdf(self._settings.csv_path)
            return pdf_bytes
        except Exception as exc:
            raise RuntimeError(f"Erro ao gerar dashboard: {exc}") from exc