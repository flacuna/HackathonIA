from __future__ import annotations

from io import BytesIO
from typing import Iterable, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    KeepInFrame,
)

from domain.models import ClusterSummary, AIStructuredOverview

# plotting
import matplotlib
matplotlib.use("Agg")  # backend não-interativo para servidores
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.patheffects as pe
import math


def build_summary_report_pdf(
    report_entries: Iterable[ClusterSummary],
    user_open_counts: Iterable[tuple[str, int]] | None = None,
    daily_open_counts: Iterable[tuple[str, int]] | None = None,
    window_total_hours: float | None = None,
    ai_overview: Optional[AIStructuredOverview] = None,
) -> bytes:
    buffer = BytesIO()
    # Layout em paisagem (horizontal) para estilo "dashboard" com mais largura útil
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=18,
        rightMargin=18,
        topMargin=18,
        bottomMargin=18,
    )
    styles = getSampleStyleSheet()

    title_style = styles["Title"]
    subtitle_style = styles["Heading2"]
    normal_style = styles["BodyText"]
    italic_style = ParagraphStyle(name="Italic", parent=normal_style, fontName="Helvetica-Oblique")

    story = [Paragraph("Relatório de Recorrência de Chamados (Operacional)", title_style), Spacer(1, 16)]

    # Se houver resumo executivo via IA, coloca no topo
    if ai_overview is not None:
        try:
            story.append(Paragraph("Resumo Executivo (IA)", subtitle_style))
            if ai_overview.periodo:
                story.append(Paragraph(f"Período: {ai_overview.periodo}", italic_style))
            if ai_overview.resumo_geral:
                story.append(Spacer(1, 6))
                story.append(Paragraph(ai_overview.resumo_geral, normal_style))
            if ai_overview.sugestoes:
                story.append(Spacer(1, 8))
                story.append(Paragraph("Sugestões de mitigação/prevenção:", styles["Heading3"]))
                story.append(
                    ListFlowable(
                        [ListItem(Paragraph(s, normal_style), leftIndent=12) for s in ai_overview.sugestoes],
                        bulletType="bullet",
                        leftIndent=0,
                    )
                )
            story.append(Spacer(1, 16))
        except Exception:
            # Se der algum erro, ignora a seção de IA
            pass

    entries: List[ClusterSummary] = list(report_entries)
    user_counts: List[tuple[str, int]] = list(user_open_counts or [])
    daily_counts: List[tuple[str, int]] = list(daily_open_counts or [])

    # Larguras de coluna para layout 2-colunas do dashboard
    col_gap = 12
    col_width = (doc.width - col_gap) / 2.0

    def _fig_to_rl_image(fig: plt.Figure, target_width: float, max_height: Optional[float] = None, dpi: int = 150) -> Image:
        """Converte um matplotlib Figure em um Image do ReportLab com largura alvo, preservando o aspecto.

        target_width e max_height estão em pontos (pt). 1in = 72pt.
        """
        w_in, h_in = fig.get_size_inches()
        aspect = h_in / w_in if w_in else 1.0
        target_height = target_width * aspect
        if max_height and target_height > max_height:
            # Reduz proporcionalmente para não ultrapassar a altura máxima
            scale = max_height / target_height
            target_width *= scale
            target_height = max_height
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        img = Image(buf, width=target_width, height=target_height)
        return img

    def _annotate_horizontal_bars(ax, labels: List[str], values: List[float]) -> None:
        """Escreve o nome dos grupos dentro da barra; se não couber, escreve ao lado.

        Regra simples: se o valor do item >= 60% do valor máximo, escreve dentro (alinhado à direita, cor branca),
        caso contrário escreve à direita da barra (alinhado à esquerda, cor preta).
        """
        if not values:
            return
        maxv = max(values) if max(values) > 0 else 1.0
        patches = ax.patches
        def _ellipsize(text: str, max_chars: int = 90) -> str:
            text = text or ""
            return text if len(text) <= max_chars else (text[: max_chars - 1] + "…")
        for patch, label, val in zip(patches, labels, values):
            x = patch.get_width()
            y = patch.get_y() + patch.get_height() / 2
            inside = val >= 0.6 * maxv
            label_draw = _ellipsize(label)
            text_effects = [pe.withStroke(linewidth=2, foreground="white")]
            if inside:
                ax.text(
                    x - 0.02 * maxv,
                    y,
                    label_draw,
                    va="center",
                    ha="right",
                    color="black",
                    fontsize=8,
                    path_effects=text_effects,
                )
            else:
                ax.text(
                    x + 0.02 * maxv,
                    y,
                    label_draw,
                    va="center",
                    ha="left",
                    color="black",
                    fontsize=8,
                    path_effects=text_effects,
                )

    if not entries:
        story.append(Paragraph("Nenhum cluster foi encontrado com os parâmetros atuais.", italic_style))
    else:
        # A tabela de grupos ficará após o dashboard; guardamos dados e seguimos
        pass

    # Visão geral do período (total de chamados e horas), quando possível
    try:
        total_tickets = None
        if user_counts:
            total_tickets = sum(c for _, c in user_counts)
        elif daily_counts:
            total_tickets = sum(c for _, c in daily_counts)
        if total_tickets is not None:
            story.append(Paragraph("Atividade no Período", subtitle_style))
            story.append(Spacer(1, 6))
            story.append(Paragraph(f"Total de chamados na janela selecionada: {total_tickets}", normal_style))
            if isinstance(window_total_hours, (int, float)):
                story.append(Paragraph(
                    f"Horas totais (soma Criado → Resolvido) na janela: {window_total_hours:,.2f}",
                    normal_style,
                ))
            story.append(Spacer(1, 12))
    except Exception:
        pass

    # ==========================
    # Dashboard (2 colunas): gráficos lado a lado quando disponíveis
    # ==========================
    dashboard_cells: List = []

    # Gráfico: Top grupos por ocorrências
    if entries:
        try:
            fig, ax = plt.subplots(figsize=(7.5, 4))
            top = entries[:10]
            sns.barplot(
                x=[e.occurrences for e in top],
                y=[e.group_name for e in top],
                palette="Blues_d",
                ax=ax,
            )
            ax.set_title("Top Grupos por Ocorrências")
            ax.set_xlabel("Ocorrências")
            ax.set_ylabel("Grupo")
            _annotate_horizontal_bars(ax, [e.representative_summary for e in top], [float(e.occurrences) for e in top])
            plt.tight_layout()

            img = _fig_to_rl_image(fig, target_width=col_width, max_height=260)
            cell = KeepInFrame(col_width, 280, [Paragraph("Top Grupos (Ocorrências)", styles["Heading3"]), Spacer(1, 4), img], mode="shrink")
            dashboard_cells.append(cell)
        except Exception:
            pass

    # ==========================
    # Gráfico: Horas gastas (top clusters com horas)
    # ==========================
    if entries:
        # Indicador de horas totais (mantido em texto, acima da tabela detalhada)
        try:
            total_hours_all = sum(e.total_hours for e in entries)
            story.append(Paragraph("Tempo total de chamados com o Mesmo Tipo em aberto", subtitle_style))
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"Quantificar o tempo total em aberto deste mesmo tipo (janela selecionada): {total_hours_all:,.2f} horas",
                normal_style,
            ))
            story.append(Spacer(1, 12))
        except Exception:
            pass

    if entries:
        try:
            top_hours = sorted(entries, key=lambda e: e.total_hours, reverse=True)[:10]
            if any(e.total_hours > 0 for e in top_hours):
                fig3, ax3 = plt.subplots(figsize=(7.5, 4))
                sns.barplot(
                    x=[e.total_hours for e in top_hours],
                    y=[e.group_name for e in top_hours],
                    palette="Reds",
                    ax=ax3,
                )
                ax3.set_title("Top Grupos por Horas em Aberto")
                ax3.set_xlabel("Horas (soma Criado → Resolvido)")
                ax3.set_ylabel("Grupo")
                _annotate_horizontal_bars(ax3, [e.representative_summary for e in top_hours], [float(e.total_hours) for e in top_hours])
                plt.tight_layout()

                img3 = _fig_to_rl_image(fig3, target_width=col_width, max_height=260)
                cell = KeepInFrame(col_width, 280, [Paragraph("Top Grupos (Horas em Aberto)", styles["Heading3"]), Spacer(1, 4), img3], mode="shrink")
                dashboard_cells.append(cell)
        except Exception:
            pass

    # ==========================
    # Gráfico: Média de horas por grupo (total_hours / ocorrências)
    # ==========================
    if entries:
        try:
            # Evita divisão por zero; occurrences normalmente >= MIN_CLUSTER_SIZE
            def _avg(e: ClusterSummary) -> float:
                return (e.total_hours / e.occurrences) if e.occurrences else 0.0

            top_avg = sorted(entries, key=_avg, reverse=True)[:10]
            if any(_avg(e) > 0 for e in top_avg):
                fig4, ax4 = plt.subplots(figsize=(7.5, 4))
                sns.barplot(
                    x=[_avg(e) for e in top_avg],
                    y=[e.group_name for e in top_avg],
                    palette="Greens",
                    ax=ax4,
                )
                ax4.set_title("Média de Horas por Grupo")
                ax4.set_xlabel("Média de horas por chamado")
                ax4.set_ylabel("Grupo")
                _annotate_horizontal_bars(ax4, [e.representative_summary for e in top_avg], [float(_avg(e)) for e in top_avg])
                plt.tight_layout()

                img4 = _fig_to_rl_image(fig4, target_width=col_width, max_height=260)
                cell = KeepInFrame(col_width, 280, [Paragraph("Média de Horas por Grupo", styles["Heading3"]), Spacer(1, 4), img4], mode="shrink")
                dashboard_cells.append(cell)
        except Exception:
            pass

    # Métrica de usuários (sempre que houver dados), independente de clusters
    if user_counts:
        try:
            top_users = user_counts[:10]
            users = [u for u, _ in top_users]
            counts = [c for _, c in top_users]
            figu, axu = plt.subplots(figsize=(7.5, 3.5))
            sns.barplot(x=counts, y=users, palette="Purples", ax=axu)
            axu.set_title("Top Usuários por Chamados")
            axu.set_xlabel("Chamados")
            axu.set_ylabel("")
            # Remover rótulos verticais (nomes no eixo Y)
            axu.set_yticklabels([])
            maxv = max(counts) if counts else 1
            # Dar espaço à direita para os nomes se estenderem além da barra
            axu.set_xlim(0, maxv * 1.35)
            pad = max(0.5, 0.02 * maxv)
            for patch, label, val in zip(axu.patches, users, counts):
                x = patch.get_x() + pad  # começa dentro da barra, à esquerda
                y = patch.get_y() + patch.get_height() / 2
                axu.text(
                    x,
                    y,
                    label,
                    va="center",
                    ha="left",
                    color="black",
                    fontsize=8,
                    path_effects=[pe.withStroke(linewidth=2, foreground="white")],
                )
            plt.tight_layout()

            imgu = _fig_to_rl_image(figu, target_width=col_width, max_height=240)
            cell = KeepInFrame(col_width, 260, [Paragraph("Top Usuários por Chamados", styles["Heading3"]), Spacer(1, 4), imgu], mode="shrink")
            dashboard_cells.append(cell)
        except Exception:
            pass

    # Série temporal: Chamados abertos por dia (linha) — sempre que houver dados
    # Renderização do dashboard em tabela 2-colunas
    if dashboard_cells:
        story.append(Paragraph("Dashboard de Indicadores", subtitle_style))
        story.append(Spacer(1, 8))
        # Cria uma tabela por linha para permitir quebra entre as linhas do dashboard
        for i in range(0, len(dashboard_cells), 2):
            left_cell = dashboard_cells[i]
            right_cell = dashboard_cells[i+1] if i+1 < len(dashboard_cells) else Spacer(1, 1)
            dash_row = Table(
                [[left_cell, right_cell]],
                colWidths=[col_width, col_width],
                style=TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ])
            )
            story.append(dash_row)
            story.append(Spacer(1, 10))
        story.append(Spacer(1, 10))

    # Série temporal (largura total)
    if daily_counts:
        try:
            days = [d for d, _ in daily_counts]
            vals = [v for _, v in daily_counts]
            xs = list(range(len(days)))
            figd, axd = plt.subplots(figsize=(9.5, 3.2))
            axd.plot(xs, vals, marker="o", color="#1f77b4")
            axd.set_title("Chamados Abertos por Dia (Janela)")
            axd.set_xlabel("Data")
            axd.set_ylabel("Chamados")
            axd.grid(True, alpha=0.3)
            # Ticks dinâmicos: no máximo ~6 rótulos distribuídos
            max_ticks = 6
            if len(xs) <= max_ticks:
                tick_idx = xs
            else:
                step = max(1, math.ceil(len(xs) / max_ticks))
                tick_idx = list(range(0, len(xs), step))
                if tick_idx[-1] != len(xs) - 1:
                    tick_idx.append(len(xs) - 1)
            axd.set_xticks(tick_idx)
            axd.set_xticklabels([days[i] for i in tick_idx], rotation=45, ha="right")
            plt.tight_layout()

            imgd = _fig_to_rl_image(figd, target_width=doc.width, max_height=240)
            story.append(Paragraph("Série Temporal de Aberturas", styles["Heading3"]))
            story.append(Spacer(1, 6))
            story.append(imgd)
            story.append(Spacer(1, 16))
        except Exception:
            pass

        # (Removido) Distribuição de tamanhos dos clusters — mantemos apenas a visualização mais acionável

    # Após o dashboard, apresentamos a tabela de grupos e detalhes
    if entries:
        story.append(Paragraph("Resumo dos principais grupos identificados", subtitle_style))
        story.append(Spacer(1, 12))

        table_data = [["Grupo", "Chamado Representativo", "Ocorrências"]]
        for entry in entries:
            table_data.append([entry.group_name, entry.representative_summary, str(entry.occurrences)])

        # Ajuste das larguras para paisagem
        table = Table(table_data, colWidths=[120, doc.width - 120 - 90, 90])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
                    ("BOX", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ]
            )
        )
        story.extend([table, Spacer(1, 18)])

    for entry in entries:
        story.append(Paragraph(entry.group_name, styles["Heading3"]))
        story.append(Paragraph(f"Chamado representativo: {entry.representative_summary}", normal_style))

        if entry.sample_summaries:
            story.append(Spacer(1, 6))
            story.append(Paragraph("Exemplos adicionais:", normal_style))
            story.append(
                ListFlowable(
                    [
                        ListItem(Paragraph(sample, normal_style), leftIndent=12)
                        for sample in entry.sample_summaries
                    ],
                    bulletType="bullet",
                    leftIndent=0,
                )
            )
        else:
            story.append(Spacer(1, 6))
            story.append(Paragraph("Nenhum outro exemplo disponível.", italic_style))

        story.append(Spacer(1, 12))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
