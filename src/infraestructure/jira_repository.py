from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Dict, Any, Optional, Tuple

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

    def get_rows_by_ids(self, ids: Iterable[str], date_range: Optional[Tuple[str, str]] = None) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        if self._df is None:
            return []
        df = self._df
        if date_range is not None:
            start, end = date_range
            # Normaliza para datas (YYYY-MM-DD) ignorando horas
            # Converte coluna 'Criado' para datetime uma vez quando necessário
            if "__Criado_date" not in df.columns:
                try:
                    df["__Criado_date"] = pd.to_datetime(df["Criado"], errors="coerce").dt.date.astype("string")
                except Exception:
                    df["__Criado_date"] = None
            mask = (df["__Criado_date"] >= str(start)) & (df["__Criado_date"] <= str(end))
            df = df[mask]

        ids_str = set(str(i) for i in ids)
        subset = df[df.index.astype(str).isin(ids_str)]
        return subset.to_dict(orient="records")

    def filter_ids_by_date(self, ids: Iterable[str], date_range: Tuple[str, str]) -> List[str]:
        """Retorna apenas os IDs contidos no intervalo (com base em 'Criado').

        date_range: (YYYY-MM-DD, YYYY-MM-DD) — horas ignoradas.
        """
        self._ensure_loaded()
        if self._df is None:
            return []
        start, end = date_range
        df = self._df
        if "__Criado_date" not in df.columns:
            try:
                df["__Criado_date"] = pd.to_datetime(df["Criado"], errors="coerce").dt.date.astype("string")
            except Exception:
                df["__Criado_date"] = None
        ids_str = set(str(i) for i in ids)
        slice_df = df[df.index.astype(str).isin(ids_str)]
        mask = (slice_df["__Criado_date"] >= str(start)) & (slice_df["__Criado_date"] <= str(end))
        return list(slice_df[mask].index.astype(str))

    def compute_total_hours(self, rows: List[Dict[str, Any]]) -> float:
        """Soma de horas entre 'Criado' e 'Resolvido' para as linhas do cluster.

        - Ignora horas informadas pelo usuário no filtro; a soma é feita com precisão de horas reais no CSV.
        - Linhas sem 'Resolvido' ou com datas inválidas são ignoradas.
        """
        total_hours = 0.0
        for r in rows:
            try:
                created = pd.to_datetime(r.get("Criado"), errors="coerce")
                resolved = pd.to_datetime(r.get("Resolvido"), errors="coerce")
                if pd.isna(created) or pd.isna(resolved):
                    continue
                delta = resolved - created
                total_hours += max(delta.total_seconds(), 0) / 3600.0
            except Exception:
                continue
        return total_hours
