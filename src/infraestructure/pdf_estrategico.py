from __future__ import annotations

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import csv
from io import BytesIO
from datetime import datetime
from typing import Iterable, List, Optional, Dict
from collections import defaultdict, Counter

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

# plotting
import matplotlib
matplotlib.use("Agg")  # backend não-interativo para servidores
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.patheffects as pe
import math


def carregar_dados_jira(caminho_csv: str) -> List[Dict]:
    """Carrega e processa dados do CSV do JIRA"""
    dados = []
    with open(caminho_csv, 'r', encoding='utf-8') as f:
        leitor = csv.DictReader(f)
        for linha in leitor:
            try:
                criado = datetime.strptime(linha['Criado'], '%Y-%m-%d %H:%M:%S')
                resolvido = datetime.strptime(linha['Resolvido'], '%Y-%m-%d %H:%M:%S')
                horas_resolucao = (resolvido - criado).total_seconds() / 3600
                
                linha['data_criacao'] = criado
                linha['data_resolucao'] = resolvido
                linha['horas_resolucao'] = horas_resolucao
                dados.append(linha)
            except:
                continue
    return dados


def analisar_desempenho_usuarios(dados: List[Dict]) -> Dict:
    """Analisa métricas de desempenho por usuário"""
    estatisticas_usuarios = defaultdict(lambda: {
        'chamados': [],
        'horas_totais': 0,
        'prioridades': Counter(),
        'tipos': Counter()
    })
    
    for linha in dados:
        criador = linha['Criador']
        estatisticas_usuarios[criador]['chamados'].append(linha)
        estatisticas_usuarios[criador]['horas_totais'] += linha['horas_resolucao']
        estatisticas_usuarios[criador]['prioridades'][linha['Prioridade']] += 1
        estatisticas_usuarios[criador]['tipos'][linha['Tipo de item']] += 1
    
    resultado = {}
    for criador, stats in estatisticas_usuarios.items():
        total_chamados = len(stats['chamados'])
        tempo_medio = stats['horas_totais'] / total_chamados if total_chamados > 0 else 0
        
        resultado[criador] = {
            'total_chamados': total_chamados,
            'tempo_medio_resolucao': tempo_medio,
            'horas_totais_trabalhadas': stats['horas_totais'],
            'distribuicao_prioridade': dict(stats['prioridades']),
            'distribuicao_tipos': dict(stats['tipos']),
            'chamados_por_dia': total_chamados / 30
        }
    
    return resultado


def build_relatorio_estrategico_pdf(caminho_csv: str) -> bytes:
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

    story = [Paragraph("Relatório Estratégico de Desempenho da Equipe", title_style), Spacer(1, 16)]

    # Carregar e analisar dados
    dados = carregar_dados_jira(caminho_csv)
    estatisticas_usuarios = analisar_desempenho_usuarios(dados)
    
    # Estatísticas gerais
    total_chamados = len(dados)
    horas_totais = sum(linha['horas_resolucao'] for linha in dados)
    tempo_medio = horas_totais / total_chamados if total_chamados > 0 else 0
    
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

    # Resumo executivo
    story.append(Paragraph("Resumo Executivo", subtitle_style))
    story.append(Spacer(1, 6))
    
    resumo_texto = f"""
    <b>Total de chamados processados:</b> {total_chamados:,}<br/>
    <b>Tempo médio de resolução:</b> {tempo_medio:.1f} horas<br/>
    <b>Total de horas investidas:</b> {horas_totais:,.1f} horas<br/>
    <b>Volume diário médio:</b> {total_chamados / 30:.1f} chamados/dia<br/>
    <b>Usuários ativos:</b> {len(estatisticas_usuarios)} pessoas
    """
    
    story.append(Paragraph(resumo_texto, normal_style))
    story.append(Spacer(1, 16))

    # ==========================
    # Dashboard (2 colunas): gráficos lado a lado quando disponíveis
    # ==========================
    dashboard_cells: List = []

    # Gráfico: Top usuários por chamados
    if estatisticas_usuarios:
        try:
            top_users = sorted(estatisticas_usuarios.items(), key=lambda x: x[1]['total_chamados'], reverse=True)[:10]
            users = [u[:15] + '...' if len(u) > 15 else u for u, _ in top_users]
            counts = [stats['total_chamados'] for _, stats in top_users]
            
            fig, ax = plt.subplots(figsize=(7.5, 4))
            sns.barplot(x=counts, y=users, palette="Blues_d", ax=ax)
            ax.set_title("Top Usuários por Chamados")
            ax.set_xlabel("Chamados")
            ax.set_ylabel("Usuário")
            plt.tight_layout()

            img = _fig_to_rl_image(fig, target_width=col_width, max_height=260)
            cell = KeepInFrame(col_width, 280, [Paragraph("Top Usuários (Chamados)", styles["Heading3"]), Spacer(1, 4), img], mode="shrink")
            dashboard_cells.append(cell)
        except Exception:
            pass

    # Gráfico: Top usuários por horas trabalhadas
    if estatisticas_usuarios:
        try:
            top_hours = sorted(estatisticas_usuarios.items(), key=lambda x: x[1]['horas_totais_trabalhadas'], reverse=True)[:10]
            users_h = [u[:15] + '...' if len(u) > 15 else u for u, _ in top_hours]
            hours = [stats['horas_totais_trabalhadas'] for _, stats in top_hours]
            
            fig3, ax3 = plt.subplots(figsize=(7.5, 4))
            sns.barplot(x=hours, y=users_h, palette="Reds", ax=ax3)
            ax3.set_title("Top Usuários por Horas Trabalhadas")
            ax3.set_xlabel("Horas Totais")
            ax3.set_ylabel("Usuário")
            plt.tight_layout()

            img3 = _fig_to_rl_image(fig3, target_width=col_width, max_height=260)
            cell = KeepInFrame(col_width, 280, [Paragraph("Top Usuários (Horas)", styles["Heading3"]), Spacer(1, 4), img3], mode="shrink")
            dashboard_cells.append(cell)
        except Exception:
            pass

    # Gráfico: Tempo médio por usuário
    if estatisticas_usuarios:
        try:
            top_avg = sorted(estatisticas_usuarios.items(), key=lambda x: x[1]['tempo_medio_resolucao'], reverse=True)[:10]
            users_avg = [u[:15] + '...' if len(u) > 15 else u for u, _ in top_avg]
            avg_times = [stats['tempo_medio_resolucao'] for _, stats in top_avg]
            
            fig4, ax4 = plt.subplots(figsize=(7.5, 4))
            sns.barplot(x=avg_times, y=users_avg, palette="Greens", ax=ax4)
            ax4.set_title("Tempo Médio de Resolução por Usuário")
            ax4.set_xlabel("Tempo Médio (horas)")
            ax4.set_ylabel("Usuário")
            plt.tight_layout()

            img4 = _fig_to_rl_image(fig4, target_width=col_width, max_height=260)
            cell = KeepInFrame(col_width, 280, [Paragraph("Tempo Médio por Usuário", styles["Heading3"]), Spacer(1, 4), img4], mode="shrink")
            dashboard_cells.append(cell)
        except Exception:
            pass

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

    # Tabela de desempenho por usuário
    story.append(Paragraph("Desempenho por Usuário", subtitle_style))
    story.append(Spacer(1, 12))

    table_data = [["Usuário", "Total Chamados", "Tempo Médio (h)", "Horas Totais", "Chamados/Dia"]]
    usuarios_ordenados = sorted(estatisticas_usuarios.items(), key=lambda x: x[1]['total_chamados'], reverse=True)
    
    for usuario, stats in usuarios_ordenados[:15]:
        table_data.append([
            usuario[:25] + '...' if len(usuario) > 25 else usuario,
            str(stats['total_chamados']),
            f"{stats['tempo_medio_resolucao']:.1f}",
            f"{stats['horas_totais_trabalhadas']:.1f}",
            f"{stats['chamados_por_dia']:.1f}"
        ])

    # Ajuste das larguras para paisagem
    table = Table(table_data, colWidths=[200, 100, 100, 100, 100])
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

    # Recomendações estratégicas
    story.append(Paragraph("Recomendações Estratégicas", subtitle_style))
    story.append(Spacer(1, 12))
    
    melhor_desempenho = max(estatisticas_usuarios.items(), key=lambda x: x[1]['total_chamados'])
    
    recomendacoes = [
        f"Usuário mais produtivo: {melhor_desempenho[0]} com {melhor_desempenho[1]['total_chamados']} chamados",
        "Considerar redistribuir carga de trabalho para equilibrar a equipe",
        f"Tempo médio de resolução atual: {tempo_medio:.1f} horas",
        "Implementar processos de automação para chamados recorrentes",
        "Revisar distribuição de prioridades e estabelecer SLAs específicos",
        "Identificar usuários com tempos elevados para capacitação"
    ]
    
    story.append(
        ListFlowable(
            [ListItem(Paragraph(rec, normal_style), leftIndent=12) for rec in recomendacoes],
            bulletType="bullet",
            leftIndent=0,
        )
    )

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
