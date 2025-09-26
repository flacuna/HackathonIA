from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

# plotting (backend não interativo para servidores)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet


def _project_csv_path() -> Path:
    """Resolve o caminho default do CSV em src/data/JIRA_limpo.csv."""
    # Este arquivo fica em src/application; subimos 2 níveis para a raiz do projeto
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "src" / "data" / "JIRA_limpo.csv"


def _load_daily_counts(csv_path: Path | None = None) -> pd.DataFrame:
    """Carrega o CSV do Jira e retorna DataFrame diário com colunas [ds(datetime64), y(int)]."""
    path = csv_path or _project_csv_path()
    if not Path(path).exists():
        raise FileNotFoundError(f"Arquivo CSV não encontrado em: {path}")
    df = pd.read_csv(path)
    if "Criado" not in df.columns:
        raise ValueError("Coluna 'Criado' não encontrada no CSV")
    df["Criado"] = pd.to_datetime(df["Criado"], errors="coerce")
    df = df.dropna(subset=["Criado"])  # remove linhas inválidas
    daily = (
        df.groupby(df["Criado"].dt.date)
          .size()
          .reset_index(name="y")
          .rename(columns={"Criado": "ds"})
    )
    # garante datetime e ordena
    daily["ds"] = pd.to_datetime(daily["Criado" if "Criado" in daily.columns else "ds"], errors="coerce")
    if "Criado" in daily.columns:
        daily = daily.drop(columns=["Criado"])
    daily = daily.sort_values("ds").reset_index(drop=True)
    return daily


def _seasonal_weekly_forecast(
    history: pd.DataFrame,
    horizon_days: int = 7,
    ci_level: float = 0.8,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gera previsão simples (ingênua) combinando tendência (MM7) + sazonalidade semanal.

    Retorna duas partes:
    - fit_hist: DataFrame com colunas [ds, yhat, yhat_lower, yhat_upper] para TODO o histórico (ajuste in-sample)
    - future:   DataFrame com colunas [ds, yhat, yhat_lower, yhat_upper] para os próximos `horizon_days` dias

    O intervalo de confiança é estimado via desvio padrão dos resíduos in-sample.
    """
    if history.empty:
        raise ValueError("Série histórica vazia para previsão")

    hist = history.copy()
    hist = hist.sort_values("ds").reset_index(drop=True)
    hist["weekday"] = hist["ds"].dt.weekday

    # Tendência: média móvel 7 dias (com fallback para média global no início)
    hist["trend"] = hist["y"].rolling(window=7, min_periods=1).mean()

    # Sazonalidade semanal: média por dia da semana, normalizada pela média global
    overall = hist["y"].mean() or 1.0
    weekly_avg = hist.groupby("weekday")["y"].mean()
    weekly_factor = (weekly_avg / overall).reindex(range(7)).fillna(1.0)

    # Ajuste in-sample para estimar resíduos
    hist["yhat_in"] = hist.apply(lambda r: r["trend"] * weekly_factor.loc[r["weekday"]], axis=1)
    resid = hist["y"] - hist["yhat_in"]
    resid_std = float(resid.std() or 1.0)

    # Z approx para alguns níveis comuns (normal padrão)
    z_map = {0.8: 1.2816, 0.9: 1.6449, 0.95: 1.96}
    z = float(z_map.get(round(ci_level, 2), 1.2816))

    fit_hist = pd.DataFrame({
        "ds": hist["ds"],
        "yhat": hist["yhat_in"],
        "yhat_lower": np.maximum(0.0, hist["yhat_in"] - z * resid_std),
        "yhat_upper": hist["yhat_in"] + z * resid_std,
    })

    last_date = hist["ds"].max()
    future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=horizon_days, freq="D")
    # Para a tendência futura, mantemos a última tendência observada (walk-forward simples)
    last_trend = float(hist["trend"].iloc[-1])

    rows = []
    for d in future_dates:
        wd = int(d.weekday())
        yhat = last_trend * float(weekly_factor.loc[wd])
        rows.append({
            "ds": d,
            "yhat": yhat,
            # IC aproximado conforme ci_level (default 80%)
            "yhat_lower": max(0.0, yhat - z * resid_std),
            "yhat_upper": yhat + z * resid_std,
        })

    future = pd.DataFrame(rows)
    return fit_hist, future


def _fig_to_image(fig: plt.Figure, width: float = 500) -> Image:
    """Converte Figure em Image (ReportLab) mantendo o aspecto.

    Calcula a altura a partir do tamanho da figura (em polegadas) para preservar a proporção.
    """
    # Calcula proporção antes de salvar
    w_in, h_in = fig.get_size_inches()
    aspect = (h_in / w_in) if w_in else 0.75  # fallback 3:4
    target_width = float(width)
    target_height = target_width * aspect

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img = Image(buf, width=target_width, height=target_height)
    return img


def _build_forecast_plots(history: pd.DataFrame, fit_hist: pd.DataFrame, future: pd.DataFrame) -> Tuple[Image, Image, Image]:
    """Cria 3 imagens: (1) histórico completo com previsão (fitted + futuro), (2) componentes, (3) zoom 10d + 7d prev."""
    # 1) Histórico + Previsão (fitted em todo o histórico + futuro)
    fig1, ax1 = plt.subplots(figsize=(12, 5))
    # Pontos observados
    ax1.scatter(history["ds"], history["y"], label="Dados Históricos Observados", color="black", s=12, alpha=0.8)
    # Linha de previsão completa (histórico ajustado + futuro)
    full_pred = pd.concat([fit_hist, future], ignore_index=True).sort_values("ds")
    ax1.plot(full_pred["ds"], full_pred["yhat"], label="Previsão (yhat)", color="#1f77b4", linewidth=1.5)
    ax1.fill_between(full_pred["ds"], full_pred["yhat_lower"], full_pred["yhat_upper"], color="#1f77b4", alpha=0.2, label="Intervalo de Confiança (80%)")
    # Linha vertical no início da previsão futura
    ax1.axvline(history["ds"].max(), color="red", linestyle="--", label="Início da Previsão")
    ax1.set_title("Previsão de Número de Issues JIRA Criadas por Dia", fontsize=14, fontweight="bold")
    ax1.set_xlabel("Data")
    ax1.set_ylabel("Número de Issues")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper left")
    plt.xticks(rotation=45)
    plt.tight_layout()
    img1 = _fig_to_image(fig1)

    # 2) Componentes: tendência (MM7) + média por dia da semana
    hist = history.copy()
    hist = hist.sort_values("ds").reset_index(drop=True)
    hist["trend"] = hist["y"].rolling(window=7, min_periods=1).mean()
    fig2, (ax21, ax22, ax23) = plt.subplots(1, 3, figsize=(16, 4))
    ax21.plot(hist["ds"], hist["trend"], color="#2ca02c")
    ax21.set_title("Tendência (MM7)")
    ax21.set_xlabel("Data")
    ax21.set_ylabel("Chamados")
    ax21.grid(True, alpha=0.3)
    # Ticks de data mais limpos
    locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
    formatter = mdates.ConciseDateFormatter(locator)
    ax21.xaxis.set_major_locator(locator)
    ax21.xaxis.set_major_formatter(formatter)

    hist["weekday"] = hist["ds"].dt.weekday
    weekly = hist.groupby("weekday")["y"].mean().reindex(range(7)).fillna(0.0)
    ax22.bar(["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"], weekly.values, color="#9467bd")
    ax22.set_title("Sazonalidade semanal (média)")
    ax22.set_ylabel("Chamados")
    ax22.grid(axis="y", alpha=0.2)

    # Padrão anual (média por mês)
    hist["month"] = hist["ds"].dt.month
    yearly = hist.groupby("month")["y"].mean().reindex(range(1, 13)).fillna(0.0)
    month_labels = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    ax23.plot(range(1, 13), yearly.values, marker="o", color="#ff7f0e")
    ax23.set_xticks(range(1, 13))
    ax23.set_xticklabels(month_labels)
    ax23.set_title("Sazonalidade anual (média por mês)")
    ax23.set_ylabel("Chamados")
    ax23.grid(True, alpha=0.2)
    plt.tight_layout()
    img2 = _fig_to_image(fig2)

    # 3) Zoom: últimos 10 dias + 7 de previsão
    last_hist = history.tail(10)
    comb = pd.concat([
        last_hist.assign(tipo="Histórico", yhat=np.nan, yhat_lower=np.nan, yhat_upper=np.nan),
        future.assign(tipo="Previsão"),
    ], ignore_index=True)
    fig3, ax3 = plt.subplots(figsize=(10, 4))
    ax3.plot(comb[comb["tipo"] == "Previsão"]["ds"], comb[comb["tipo"] == "Previsão"]["yhat"], label="Previsão", color="#1f77b4")
    ax3.fill_between(
        comb[comb["tipo"] == "Previsão"]["ds"],
        comb[comb["tipo"] == "Previsão"]["yhat_lower"],
        comb[comb["tipo"] == "Previsão"]["yhat_upper"],
        color="#1f77b4",
        alpha=0.2,
        label="IC 80%",
    )
    ax3.scatter(last_hist["ds"], last_hist["y"], label="Últimos 10 dias (reais)", color="#000", zorder=5)
    ax3.axvline(last_hist["ds"].max(), color="red", linestyle="--", label="Início da previsão")
    ax3.set_title("Zoom: últimos 10 dias + 7 previstos")
    ax3.set_xlabel("Data")
    ax3.set_ylabel("Chamados")
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    img3 = _fig_to_image(fig3)

    return img1, img2, img3


def generate_forecast_pdf(horizon_days: int = 7) -> bytes:
    """Gera um PDF com as previsões de chamados para os próximos dias.

    - Lê o CSV em src/data/JIRA_limpo.csv
    - Agrega por dia
    - Aplica modelo simples (MM7 + sazonalidade semanal)
    - Monta relatório em PDF com 3 gráficos principais
    """
    history = _load_daily_counts()
    fit_hist, future = _seasonal_weekly_forecast(history, horizon_days=horizon_days, ci_level=0.8)
    img1, img2, img3 = _build_forecast_plots(history, fit_hist, future)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Relatório de Previsão de Chamados", styles["Title"]))
    story.append(Spacer(1, 12))
    start_date = history["ds"].min().date()
    end_date = history["ds"].max().date()
    story.append(Paragraph(f"Histórico considerado: {start_date} até {end_date}", styles["Normal"]))
    story.append(Paragraph(f"Horizonte da previsão: {horizon_days} dias", styles["Normal"]))
    story.append(Spacer(1, 18))

    story.append(Paragraph("Histórico + Previsão", styles["Heading2"]))
    story.append(Spacer(1, 6))
    story.append(img1)
    story.append(Spacer(1, 18))

    story.append(Paragraph("Componentes (tendência e semanal)", styles["Heading2"]))
    story.append(Spacer(1, 6))
    story.append(img2)
    story.append(Spacer(1, 18))

    story.append(Paragraph("Zoom: últimos 10 dias + previsão", styles["Heading2"]))
    story.append(Spacer(1, 6))
    story.append(img3)

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf
