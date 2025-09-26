from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import chromadb

from application.summary_service import SummaryServiceSettings


@dataclass(frozen=True)
class ChromaHealth:
    chroma_path: str
    collection_name: str
    exists: bool
    count: Optional[int]
    error: Optional[str]


class HealthService:
    def __init__(self, settings: SummaryServiceSettings) -> None:
        self._settings = settings

    def check_chroma(self) -> ChromaHealth:
        try:
            client = chromadb.PersistentClient(path=self._settings.chroma_path)
            # Não criar automaticamente; apenas tenta obter
            collection = client.get_collection(name=self._settings.collection_name)
            count = collection.count()
            return ChromaHealth(
                chroma_path=self._settings.chroma_path,
                collection_name=self._settings.collection_name,
                exists=True,
                count=count,
                error=None,
            )
        except Exception as exc:
            return ChromaHealth(
                chroma_path=self._settings.chroma_path,
                collection_name=self._settings.collection_name,
                exists=False,
                count=None,
                error=str(exc),
            )
