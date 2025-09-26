from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Optional, Protocol, Dict, Any, Tuple
from collections import Counter

import chromadb

from domain.models import ClusterSummary, AIStructuredOverview


class JiraRepository(Protocol):
    def get_rows_by_ids(self, ids: Iterable[str], date_range: Optional[tuple[str, str]] = None) -> List[Dict[str, Any]]: ...
    def filter_ids_by_date(self, ids: Iterable[str], date_range: tuple[str, str]) -> List[str]: ...


@dataclass(frozen=True)
class SummaryServiceSettings:
    chroma_path: str
    collection_name: str = "chamados_jira"
    distance_threshold: float = 1.0
    min_cluster_size: int = 3
    max_neighbors: int = 200
    max_clusters: int = 20
    create_if_missing: bool = False


class SummaryReportService:
    def __init__(
        self,
        settings: SummaryServiceSettings,
        jira_repo: Optional[JiraRepository] = None,
        bedrock_client: Any | None = None,
    ) -> None:
        self._settings = settings
        self._client = chromadb.PersistentClient(path=settings.chroma_path)
        # Por padrão, não cria coleção automaticamente (evita a impressão de que a base foi "recriada")
        if settings.create_if_missing:
            self._collection = self._client.get_or_create_collection(name=settings.collection_name)
        else:
            try:
                self._collection = self._client.get_collection(name=settings.collection_name)
            except Exception as exc:
                raise RuntimeError(
                    "Coleção Chroma não encontrada. Configure CHROMA_DB_PATH/CHROMA_COLLECTION_NAME para apontar para uma base existente"
                ) from exc
        self._jira_repo = jira_repo
        self._bedrock = bedrock_client

    def generate_cluster_report(
        self, data_inicio: Optional[str] = None, data_fim: Optional[str] = None
    ) -> Tuple[List[ClusterSummary], List[Tuple[str, int]], List[Tuple[str, int]], float]:
        all_items = self._collection.get(include=["embeddings", "metadatas"])  # ids vem por padrão
        all_ids: Sequence[str] = all_items.get("ids", [])

        if not all_ids:
            return [], [], [], 0.0

        embeddings = all_items.get("embeddings", [])
        embeddings_map = {item_id: embedding for item_id, embedding in zip(all_ids, embeddings)}

        # Se data_inicio e data_fim forem fornecidas e tivermos repositório CSV,
        # filtramos IDs fora da janela ANTES do clustering
        if data_inicio and data_fim and self._jira_repo is not None:
            try:
                filtered_ids = set(self._jira_repo.filter_ids_by_date(all_ids, (data_inicio, data_fim)))
                all_ids = [i for i in all_ids if i in filtered_ids]
            except Exception:
                # Se o filtro falhar por motivo do CSV, segue sem filtrar
                pass

        # Estatística por usuário (Criador) respeitando a janela
        user_open_counts: List[Tuple[str, int]] = []
        daily_open_counts: List[Tuple[str, int]] = []
        window_total_hours: float = 0.0
        if self._jira_repo is not None:
            try:
                date_range = (data_inicio, data_fim) if data_inicio and data_fim else None
                rows_all = self._jira_repo.get_rows_by_ids(all_ids, date_range=date_range)
                counter = Counter()
                for row in rows_all:
                    creator = row.get("Criador") or row.get("criador") or row.get("author")
                    if isinstance(creator, str) and creator.strip():
                        counter[creator.strip()] += 1
                user_open_counts = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)

                # Contagem diária de aberturas (com base em '__Criado_date' quando disponível)
                day_counter = Counter()
                for row in rows_all:
                    day = row.get("__Criado_date")
                    if not day:
                        # fallback: parse de 'Criado' e extrai a data
                        val = row.get("Criado")
                        if isinstance(val, str) and val:
                            try:
                                day = str(val[:10])
                            except Exception:
                                day = None
                    if isinstance(day, str) and day:
                        day_counter[day] += 1
                daily_open_counts = sorted(day_counter.items(), key=lambda kv: kv[0])

                # Soma de horas na janela (Criado -> Resolvido) em todas as linhas
                try:
                    window_total_hours = self._jira_repo.compute_total_hours(rows_all)
                except Exception:
                    window_total_hours = 0.0
            except Exception:
                user_open_counts = []
                daily_open_counts = []
                window_total_hours = 0.0

        clusters: List[List[str]] = []
        unclustered_ids = set(all_ids)

        while unclustered_ids:
            seed_id = next(iter(unclustered_ids))
            unclustered_ids.remove(seed_id)

            current_cluster = {seed_id}
            seed_embedding = embeddings_map[seed_id]

            neighbors = self._collection.query(
                query_embeddings=[seed_embedding],
                n_results=self._settings.max_neighbors,
                include=["distances"],
            )

            neighbor_ids = neighbors.get("ids", [[]])[0]
            distances = neighbors.get("distances", [[]])[0]

            for neighbor_id, distance in zip(neighbor_ids, distances):
                if neighbor_id in unclustered_ids and distance <= self._settings.distance_threshold:
                    current_cluster.add(neighbor_id)
                    unclustered_ids.remove(neighbor_id)

            if len(current_cluster) >= self._settings.min_cluster_size:
                clusters.append(list(current_cluster))

        clusters.sort(key=len, reverse=True)

        report_entries: List[ClusterSummary] = []

        for index, cluster_ids in enumerate(clusters[: self._settings.max_clusters], start=1):
            metadatas = self._collection.get(ids=cluster_ids, include=["metadatas"]).get("metadatas", [])
            representative_summary = self._extract_summary(metadatas)

            # Enriquecer com CSV se disponível
            csv_summaries: List[str] = []
            total_hours: float = 0.0
            if self._jira_repo is not None:
                try:
                    date_range = (data_inicio, data_fim) if data_inicio and data_fim else None
                    rows = self._jira_repo.get_rows_by_ids(cluster_ids, date_range=date_range)
                    csv_summaries = self._extract_summaries_from_rows(rows, limit=5)
                    try:
                        total_hours = self._jira_repo.compute_total_hours(rows)
                    except Exception:
                        total_hours = 0.0
                except Exception:
                    # Não impede a geração do relatório; segue apenas com metadados
                    csv_summaries = []
                    total_hours = 0.0

            # Se o resumo representativo não veio dos metadados, tenta cair para o CSV
            if (not representative_summary) or representative_summary == "Nome não encontrado":
                if csv_summaries:
                    representative_summary = csv_summaries[0]

            sample_from_meta = self._extract_sample_summaries(
                metadatas, limit=3, skip=representative_summary
            )
            # Complementa com exemplos do CSV (evitando duplicatas)
            sample_from_csv = [
                s for s in csv_summaries if s and s.strip() and s.strip() != representative_summary
            ]
            sample_summaries = (sample_from_meta + sample_from_csv)[:3]

            report_entries.append(
                ClusterSummary(
                    group_name=f"Grupo {index}",
                    representative_summary=representative_summary,
                    occurrences=len(cluster_ids),
                    sample_summaries=sample_summaries,
                    total_hours=total_hours,
                )
            )

        return report_entries, user_open_counts, daily_open_counts, window_total_hours

    def generate_structured_overview(
        self,
        report_entries: List[ClusterSummary],
        user_open_counts: List[Tuple[str, int]] | None,
        daily_open_counts: List[Tuple[str, int]] | None,
        data_inicio: Optional[str],
        data_fim: Optional[str],
    ) -> Optional[AIStructuredOverview]:
        """Chama o cliente Bedrock/Anthropic para produzir um resumo estruturado em PT-BR.

        Retorna None se o cliente não estiver configurado (para permitir funcionamento offline).
        """
        if not self._bedrock:
            return None
        try:
            data = self._bedrock.generate_structured_overview_pt(
                report_entries=report_entries,
                user_open_counts=user_open_counts,
                daily_open_counts=daily_open_counts,
                data_inicio=data_inicio,
                data_fim=data_fim,
            )
            periodo = str(data.get("periodo", ""))
            resumo_geral = str(data.get("resumo_geral", ""))
            sugestoes = [str(s) for s in (data.get("sugestoes") or []) if isinstance(s, str)]
            return AIStructuredOverview(periodo=periodo, resumo_geral=resumo_geral, sugestoes=sugestoes)
        except Exception:
            return None

    @staticmethod
    def _extract_summary(metadatas: Iterable[dict]) -> str:
        summary_keys = ("resumo", "Resumo", "summary", "Summary", "title")
        for metadata in metadatas:
            for key in summary_keys:
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return "Nome não encontrado"

    @staticmethod
    def _extract_sample_summaries(metadatas: Iterable[dict], limit: int, skip: str) -> List[str]:
        summaries: List[str] = []
        summary_keys = ("resumo", "Resumo", "summary", "Summary", "title")
        normalized_skip = skip.strip().lower() if isinstance(skip, str) else ""

        for metadata in metadatas:
            for key in summary_keys:
                value = metadata.get(key)
                if isinstance(value, str):
                    normalized_value = value.strip()
                    if normalized_value and normalized_value.lower() != normalized_skip:
                        summaries.append(normalized_value)
                        break
            if len(summaries) >= limit:
                break

        return summaries

    @staticmethod
    def _extract_summaries_from_rows(rows: Iterable[Dict[str, Any]], limit: int) -> List[str]:
        keys = ("Resumo", "resumo", "summary", "Summary", "Descrição", "descricao")
        out: List[str] = []
        for row in rows:
            for key in keys:
                value = row.get(key)
                if isinstance(value, str) and value.strip():
                    out.append(value.strip())
                    break
            if len(out) >= limit:
                break
        return out
