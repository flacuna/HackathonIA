from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from application.summary_service import SummaryReportService, SummaryServiceSettings


def _parse_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@lru_cache
def get_summary_settings() -> SummaryServiceSettings:
    project_root = Path(__file__).resolve().parent.parent
    default_chroma_path = project_root / "chroma_db"

    return SummaryServiceSettings(
        chroma_path=os.getenv("CHROMA_DB_PATH", str(default_chroma_path)),
        collection_name=os.getenv("CHROMA_COLLECTION_NAME", "chamados_jira"),
        distance_threshold=_parse_float(os.getenv("SUMMARY_DISTANCE_THRESHOLD", "1.0"), 1.0),
        min_cluster_size=_parse_int(os.getenv("SUMMARY_MIN_CLUSTER_SIZE", "3"), 3),
        max_neighbors=_parse_int(os.getenv("SUMMARY_MAX_NEIGHBORS", "200"), 200),
        max_clusters=_parse_int(os.getenv("SUMMARY_MAX_CLUSTERS", "20"), 20),
    )


@lru_cache
def get_summary_service() -> SummaryReportService:
    settings = get_summary_settings()
    return SummaryReportService(settings)


def get_summary_service_dependency() -> SummaryReportService:
    return get_summary_service()
