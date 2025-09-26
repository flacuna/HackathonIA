from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

import chromadb

from domain.models import ClusterSummary


@dataclass(frozen=True)
class SummaryServiceSettings:
    chroma_path: str
    collection_name: str = "chamados_jira"
    distance_threshold: float = 1.0
    min_cluster_size: int = 3
    max_neighbors: int = 200
    max_clusters: int = 20


class SummaryReportService:
    def __init__(self, settings: SummaryServiceSettings) -> None:
        self._settings = settings
        self._client = chromadb.PersistentClient(path=settings.chroma_path)
        self._collection = self._client.get_collection(name=settings.collection_name)

    def generate_cluster_report(self) -> List[ClusterSummary]:
        all_items = self._collection.get(include=["embeddings", "metadatas"])
        all_ids: Sequence[str] = all_items.get("ids", [])

        if not all_ids:
            return []

        embeddings = all_items.get("embeddings", [])
        embeddings_map = {item_id: embedding for item_id, embedding in zip(all_ids, embeddings)}

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
            sample_summaries = self._extract_sample_summaries(metadatas, limit=3, skip=representative_summary)

            report_entries.append(
                ClusterSummary(
                    group_name=f"Grupo {index}",
                    representative_summary=representative_summary,
                    occurrences=len(cluster_ids),
                    sample_summaries=sample_summaries,
                )
            )

        return report_entries

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
