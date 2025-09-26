from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class ClusterSummary:
    """Representa um agrupamento de chamados similares."""

    group_name: str
    representative_summary: str
    occurrences: int
    sample_summaries: List[str]
    total_hours: float = 0.0


@dataclass(frozen=True)
class AIStructuredOverview:
    """Resumo executivo estruturado gerado por LLM.

    - periodo: texto com o range de data respeitado (ex: "2025-09-01 a 2025-09-25")
    - resumo_geral: visão geral em PT-BR dos tickets abertos na janela
    - sugestoes: lista de ações de mitigação/prevenção
    """

    periodo: str
    resumo_geral: str
    sugestoes: List[str]
