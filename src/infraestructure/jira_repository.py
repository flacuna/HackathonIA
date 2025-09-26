from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Dict, Any, Optional

import pandas as pd


class JiraCsvRepository:
    """Acesso ao CSV do Jira, com carregamento preguiçoso (lazy).

    - Caminho padrão: src/data/JIRA_limpo.csv (pode ser sobrescrito via env JIRA_CSV_PATH)
    - O arquivo só é carregado quando for necessário (get_rows_by_ids)
    """

    def __init__(self, csv_path: Optional[str] = None) -> None:
        self._csv_path = csv_path or os.getenv("JIRA_CSV_PATH")
        self._df = None  # type: Optional[pd.DataFrame]

    @property
    def csv_path(self) -> Optional[str]:
        if self._csv_path:
            return self._csv_path
        # default para src/data/JIRA_limpo.csv
        project_root = Path(__file__).resolve().parents[2]
        default_path = project_root / "src" / "data" / "JIRA_limpo.csv"
        return str(default_path)

    def _ensure_loaded(self) -> None:
        if self._df is not None:
            return
        path = self.csv_path
        if not path or not Path(path).exists():
            # sem arquivo disponível, segue sem carregar
            self._df = None
            return
        df = pd.read_csv(path, sep=",")
        # garante índice como string para casar com IDs textuais
        df.index = df.index.astype(str)
        self._df = df

    def available(self) -> bool:
        path = self.csv_path
        return bool(path and Path(path).exists())

    def get_rows_by_ids(self, ids: Iterable[str]) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        if self._df is None:
            return []
        ids_str = set(str(i) for i in ids)
        subset = self._df[self._df.index.astype(str).isin(ids_str)]
        return subset.to_dict(orient="records")
