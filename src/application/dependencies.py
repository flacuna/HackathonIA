from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from application.summary_service import SummaryReportService, SummaryServiceSettings
from infraestructure.jira_repository import JiraCsvRepository
from infraestructure.llm_bedrock import BedrockAnthropicClient


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
    default_chroma_path = project_root / "data" / "chroma_db"

    return SummaryServiceSettings(
        chroma_path=os.getenv("CHROMA_DB_PATH", str(default_chroma_path)),
        collection_name=os.getenv("CHROMA_COLLECTION_NAME", "chamados_jira"),
        distance_threshold=_parse_float(os.getenv("SUMMARY_DISTANCE_THRESHOLD", "1.0"), 1.0),
        min_cluster_size=_parse_int(os.getenv("SUMMARY_MIN_CLUSTER_SIZE", "3"), 3),
        max_neighbors=_parse_int(os.getenv("SUMMARY_MAX_NEIGHBORS", "200"), 200),
        max_clusters=_parse_int(os.getenv("SUMMARY_MAX_CLUSTERS", "20"), 20),
        create_if_missing=os.getenv("CHROMA_CREATE_IF_MISSING", "false").lower() in {"1", "true", "yes"},
    )


@lru_cache
def get_summary_service() -> SummaryReportService:
    settings = get_summary_settings()
    # Repositório CSV padrão aponta a src/data/JIRA_limpo.csv (sobrescrevível por JIRA_CSV_PATH)
    jira_repo = JiraCsvRepository()
    # Cliente Bedrock/Anthropic opcional. Se não houver credenciais/região, seguirá sem IA.
    bedrock = None
    try:
        bedrock = BedrockAnthropicClient()
    except Exception:
        bedrock = None
    return SummaryReportService(settings, jira_repo=jira_repo, bedrock_client=bedrock)


def get_summary_service_dependency() -> SummaryReportService:
    return get_summary_service()
