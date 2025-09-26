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
