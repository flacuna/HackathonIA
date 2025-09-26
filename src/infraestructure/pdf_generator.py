from __future__ import annotations

from io import BytesIO
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from domain.models import ClusterSummary


def build_summary_report_pdf(report_entries: Iterable[ClusterSummary]) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    title_style = styles["Title"]
    subtitle_style = styles["Heading2"]
    normal_style = styles["BodyText"]
    italic_style = ParagraphStyle(name="Italic", parent=normal_style, fontName="Helvetica-Oblique")

    story = [Paragraph("Relatório de Recorrência de Chamados", title_style), Spacer(1, 16)]

    entries = list(report_entries)

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
