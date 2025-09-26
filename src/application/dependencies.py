from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from application.summary_service import SummaryReportService, SummaryServiceSettings
from application.estrategico_service import EstrategicoReportService, EstrategicoServiceSettings
from application.dashboard_service import DashboardReportService, DashboardServiceSettings
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


@lru_cache
def get_estrategico_settings() -> EstrategicoServiceSettings:
    project_root = Path(__file__).resolve().parent.parent
    default_csv_path = project_root / "data" / "JIRA_limpo.csv"
    
    return EstrategicoServiceSettings(
        csv_path=os.getenv("JIRA_CSV_PATH", str(default_csv_path))
    )


@lru_cache
def get_estrategico_service() -> EstrategicoReportService:
    settings = get_estrategico_settings()
    jira_repo = JiraCsvRepository()
    return EstrategicoReportService(settings, jira_repo=jira_repo)


@lru_cache
def get_dashboard_settings() -> DashboardServiceSettings:
    project_root = Path(__file__).resolve().parent.parent
    default_csv_path = project_root / "data" / "JIRA_limpo.csv"
    
    return DashboardServiceSettings(
        csv_path=os.getenv("JIRA_CSV_PATH", str(default_csv_path))
    )


@lru_cache
def get_dashboard_service() -> DashboardReportService:
    settings = get_dashboard_settings()
    jira_repo = JiraCsvRepository()
    return DashboardReportService(settings, jira_repo=jira_repo)


def get_summary_service_dependency() -> SummaryReportService:
    return get_summary_service()


def get_estrategico_service_dependency() -> EstrategicoReportService:
    return get_estrategico_service()


def get_dashboard_service_dependency() -> DashboardReportService:
    return get_dashboard_service()
