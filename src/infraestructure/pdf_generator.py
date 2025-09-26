from __future__ import annotations

from io import BytesIO
from typing import Iterable, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
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
)

from domain.models import ClusterSummary

# plotting
import matplotlib
matplotlib.use("Agg")  # backend não-interativo para servidores
import matplotlib.pyplot as plt
import seaborn as sns


def build_summary_report_pdf(
    report_entries: Iterable[ClusterSummary],
    user_open_counts: Iterable[tuple[str, int]] | None = None,
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    title_style = styles["Title"]
    subtitle_style = styles["Heading2"]
    normal_style = styles["BodyText"]
    italic_style = ParagraphStyle(name="Italic", parent=normal_style, fontName="Helvetica-Oblique")

    story = [Paragraph("Relatório de Recorrência de Chamados", title_style), Spacer(1, 16)]

    entries: List[ClusterSummary] = list(report_entries)
    user_counts: List[tuple[str, int]] = list(user_open_counts or [])

    if not entries:
        story.append(Paragraph("Nenhum cluster foi encontrado com os parâmetros atuais.", italic_style))
    else:
        story.append(Paragraph("Resumo dos principais grupos identificados", subtitle_style))
        story.append(Spacer(1, 12))

        table_data = [["Grupo", "Chamado Representativo", "Ocorrências"]]
        for entry in entries:
            table_data.append([entry.group_name, entry.representative_summary, str(entry.occurrences)])

        table = Table(table_data, colWidths=[70, 340, 80])
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

    # ==========================
    # Gráfico: Top grupos por ocorrências
    # ==========================
        try:
            fig, ax = plt.subplots(figsize=(7.5, 4))  # largura próxima da página A4
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
            plt.tight_layout()

            img_buf = BytesIO()
            fig.savefig(img_buf, format="png", dpi=150, bbox_inches="tight")
            plt.close(fig)
            img_buf.seek(0)

            story.append(Paragraph("Visualização: Top Grupos (Ocorrências)", styles["Heading3"]))
            story.append(Spacer(1, 6))
            story.append(Image(img_buf, width=480, height=256))
            story.append(Spacer(1, 18))
        except Exception:
            # Se der qualquer erro no gráfico, seguimos apenas com a tabela
            pass

        # ==========================
        # Gráfico: Horas gastas (top clusters com horas)
        # ==========================

        # Horas totais após o resumo de grupos
        try:
            total_hours_all = sum(e.total_hours for e in entries)
            story.append(Paragraph("Horas Gastas com o Mesmo Tipo", subtitle_style))
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"Quantificar as horas gastas com este mesmo tipo (janela selecionada): {total_hours_all:,.2f} horas",
                normal_style,
            ))
            story.append(Spacer(1, 12))
        except Exception:
            pass

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
                ax3.set_title("Top Grupos por Horas Gastas")
                ax3.set_xlabel("Horas (soma Criado → Resolvido)")
                ax3.set_ylabel("Grupo")
                plt.tight_layout()

                img_buf3 = BytesIO()
                fig3.savefig(img_buf3, format="png", dpi=150, bbox_inches="tight")
                plt.close(fig3)
                img_buf3.seek(0)

                story.append(Paragraph("Visualização: Top Grupos (Horas Gastas)", styles["Heading3"]))
                story.append(Spacer(1, 6))
                story.append(Image(img_buf3, width=480, height=256))
                story.append(Spacer(1, 18))
        except Exception:
            pass

        # ==========================
        # Gráfico: Média de horas por grupo (total_hours / ocorrências)
        # ==========================
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
                plt.tight_layout()

                img_buf4 = BytesIO()
                fig4.savefig(img_buf4, format="png", dpi=150, bbox_inches="tight")
                plt.close(fig4)
                img_buf4.seek(0)

                story.append(Paragraph("Visualização: Média de Horas por Grupo", styles["Heading3"]))
                story.append(Spacer(1, 6))
                story.append(Image(img_buf4, width=480, height=256))
                story.append(Spacer(1, 18))
        except Exception:
            pass

        # Após as visualizações por grupo, inserir métrica de usuários
        if user_counts:
            try:
                story.append(Paragraph("Chamados Abertos por Usuário (Top)", subtitle_style))
                story.append(Spacer(1, 8))
                top_users = user_counts[:10]

                table_user = Table([["Usuário", "Chamados"]] + [[u, str(c)] for u, c in top_users], colWidths=[300, 90])
                table_user.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F4F4F")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
                        ("BOX", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ])
                )
                story.extend([table_user, Spacer(1, 14)])

                figu, axu = plt.subplots(figsize=(7.5, 3.5))
                sns.barplot(x=[c for _, c in top_users], y=[u for u, _ in top_users], palette="Purples", ax=axu)
                axu.set_title("Top Usuários por Chamados Abertos")
                axu.set_xlabel("Chamados")
                axu.set_ylabel("Usuário")
                plt.tight_layout()
                bufu = BytesIO()
                figu.savefig(bufu, format="png", dpi=150, bbox_inches="tight")
                plt.close(figu)
                bufu.seek(0)
                story.append(Image(bufu, width=480, height=220))
                story.append(Spacer(1, 18))
            except Exception:
                pass

        # (Removido) Distribuição de tamanhos dos clusters — mantemos apenas a visualização mais acionável

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
