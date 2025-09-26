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


def analisar_causas_raizes(dados: List[Dict]) -> Dict:
    """Analisa as principais causas raízes dos problemas"""
    # Análise por tipo de projeto
    projetos = Counter(linha['Tipo de projeto'] for linha in dados)
    
    # Análise por prioridade
    prioridades = Counter(linha['Prioridade'] for linha in dados)
    
    # Análise por tipo de item
    tipos_item = Counter(linha['Tipo de item'] for linha in dados)
    
    # Análise temporal - problemas por mês
    problemas_mensais = defaultdict(int)
    for linha in dados:
        mes = linha['data_criacao'].strftime('%Y-%m')
        problemas_mensais[mes] += 1
    
    # Análise de tempo de resolução por categoria
    tempo_por_projeto = defaultdict(list)
    tempo_por_prioridade = defaultdict(list)
    
    for linha in dados:
        tempo_por_projeto[linha['Tipo de projeto']].append(linha['horas_resolucao'])
        tempo_por_prioridade[linha['Prioridade']].append(linha['horas_resolucao'])
    
    # Calcular médias
    tempo_medio_projeto = {
        projeto: sum(tempos) / len(tempos) if tempos else 0
        for projeto, tempos in tempo_por_projeto.items()
    }
    
    tempo_medio_prioridade = {
        prioridade: sum(tempos) / len(tempos) if tempos else 0
        for prioridade, tempos in tempo_por_prioridade.items()
    }
    
    return {
        'projetos': dict(projetos),
        'prioridades': dict(prioridades),
        'tipos_item': dict(tipos_item),
        'problemas_mensais': dict(problemas_mensais),
        'tempo_medio_projeto': tempo_medio_projeto,
        'tempo_medio_prioridade': tempo_medio_prioridade,
        'total_chamados': len(dados),
        'tempo_total': sum(linha['horas_resolucao'] for linha in dados)
    }


def calcular_kpis_presidencia(dados: List[Dict]) -> Dict:
    """Calcula KPIs executivos para a presidência"""
    total_chamados = len(dados)
    tempo_total = sum(linha['horas_resolucao'] for linha in dados)
    tempo_medio = tempo_total / total_chamados if total_chamados > 0 else 0
    
    # KPIs de eficiência
    chamados_alta_prioridade = len([d for d in dados if d['Prioridade'] in ['High', 'Highest', 'Critical']])
    percentual_alta_prioridade = (chamados_alta_prioridade / total_chamados * 100) if total_chamados > 0 else 0
    
    # KPIs de produtividade
    usuarios_unicos = len(set(linha['Criador'] for linha in dados))
    chamados_por_usuario = total_chamados / usuarios_unicos if usuarios_unicos > 0 else 0
    
    # KPIs de qualidade (tempo de resolução)
    tempos_resolucao = [linha['horas_resolucao'] for linha in dados]
    tempo_mediano = sorted(tempos_resolucao)[len(tempos_resolucao)//2] if tempos_resolucao else 0
    
    return {
        'total_chamados': total_chamados,
        'tempo_medio_resolucao': tempo_medio,
        'tempo_mediano_resolucao': tempo_mediano,
        'percentual_alta_prioridade': percentual_alta_prioridade,
        'usuarios_ativos': usuarios_unicos,
        'produtividade_media': chamados_por_usuario,
        'custo_total_horas': tempo_total,
        'eficiencia_diaria': total_chamados / 30
    }


def build_relatorio_causas_raizes_pdf(caminho_csv: str) -> bytes:
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

    story = [Paragraph("Relatório de Causas Raízes e KPIs Executivos", title_style), Spacer(1, 16)]

    # Carregar e analisar dados
    dados = carregar_dados_jira(caminho_csv)
    causas_raizes = analisar_causas_raizes(dados)
    kpis = calcular_kpis_presidencia(dados)
    
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

    # KPIs Executivos
    story.append(Paragraph("KPIs Executivos - Dashboard da Presidência", subtitle_style))
    story.append(Spacer(1, 6))
    
    kpis_texto = f"""
    <b>Total de Chamados:</b> {kpis['total_chamados']:,}<br/>
    <b>Tempo Médio de Resolução:</b> {kpis['tempo_medio_resolucao']:.1f} horas<br/>
    <b>Eficiência Diária:</b> {kpis['eficiencia_diaria']:.1f} chamados/dia<br/>
    <b>Chamados Alta Prioridade:</b> {kpis['percentual_alta_prioridade']:.1f}%<br/>
    <b>Produtividade Média:</b> {kpis['produtividade_media']:.1f} chamados/usuário<br/>
    <b>Custo Total (Horas):</b> {kpis['custo_total_horas']:,.1f} horas
    """
    
    story.append(Paragraph(kpis_texto, normal_style))
    story.append(Spacer(1, 16))

    # ==========================
    # Dashboard (2 colunas): gráficos lado a lado quando disponíveis
    # ==========================
    dashboard_cells: List = []

    # Gráfico: Principais causas por tipo de projeto
    if causas_raizes['projetos']:
        try:
            projetos_sorted = sorted(causas_raizes['projetos'].items(), key=lambda x: x[1], reverse=True)[:8]
            proj_names = [p[:20] + '...' if len(p) > 20 else p for p, _ in projetos_sorted]
            proj_counts = [c for _, c in projetos_sorted]
            
            fig, ax = plt.subplots(figsize=(7.5, 4))
            sns.barplot(x=proj_counts, y=proj_names, palette="Reds", ax=ax)
            ax.set_title("Principais Causas por Tipo de Projeto")
            ax.set_xlabel("Número de Chamados")
            ax.set_ylabel("Tipo de Projeto")
            plt.tight_layout()

            img = _fig_to_rl_image(fig, target_width=col_width, max_height=260)
            cell = KeepInFrame(col_width, 280, [Paragraph("Causas por Projeto", styles["Heading3"]), Spacer(1, 4), img], mode="shrink")
            dashboard_cells.append(cell)
        except Exception:
            pass

    # Gráfico: Distribuição por prioridade
    if causas_raizes['prioridades']:
        try:
            prio_sorted = sorted(causas_raizes['prioridades'].items(), key=lambda x: x[1], reverse=True)
            prio_names = [p for p, _ in prio_sorted]
            prio_counts = [c for _, c in prio_sorted]
            
            fig2, ax2 = plt.subplots(figsize=(7.5, 4))
            colors_prio = ['#d62728', '#ff7f0e', '#2ca02c', '#1f77b4', '#9467bd'][:len(prio_names)]
            ax2.pie(prio_counts, labels=prio_names, autopct='%1.1f%%', colors=colors_prio)
            ax2.set_title("Distribuição por Prioridade")
            plt.tight_layout()

            img2 = _fig_to_rl_image(fig2, target_width=col_width, max_height=260)
            cell = KeepInFrame(col_width, 280, [Paragraph("Distribuição Prioridades", styles["Heading3"]), Spacer(1, 4), img2], mode="shrink")
            dashboard_cells.append(cell)
        except Exception:
            pass

    # Renderização do dashboard em tabela 2-colunas
    if dashboard_cells:
        story.append(Paragraph("Dashboard de Análise de Causas Raízes", subtitle_style))
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

    # Análise de Causas Raízes
    story.append(Paragraph("Análise de Causas Raízes", subtitle_style))
    story.append(Spacer(1, 12))

    # Tabela de principais causas
    table_data = [["Categoria", "Tipo", "Ocorrências", "% do Total", "Tempo Médio (h)"]]
    
    # Adicionar dados de projetos
    total_chamados = causas_raizes['total_chamados']
    for projeto, count in sorted(causas_raizes['projetos'].items(), key=lambda x: x[1], reverse=True)[:10]:
        percentual = (count / total_chamados * 100) if total_chamados > 0 else 0
        tempo_medio = causas_raizes['tempo_medio_projeto'].get(projeto, 0)
        table_data.append([
            "Projeto",
            projeto[:30] + '...' if len(projeto) > 30 else projeto,
            str(count),
            f"{percentual:.1f}%",
            f"{tempo_medio:.1f}"
        ])

    # Ajuste das larguras para paisagem
    table = Table(table_data, colWidths=[80, 250, 80, 80, 80])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
                ("BOX", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ]
        )
    )
    story.extend([table, Spacer(1, 18)])

    # Recomendações para Investimentos
    story.append(Paragraph("Recomendações de Investimento", subtitle_style))
    story.append(Spacer(1, 12))
    
    # Identificar principais problemas
    principal_projeto = max(causas_raizes['projetos'].items(), key=lambda x: x[1])
    projeto_mais_lento = max(causas_raizes['tempo_medio_projeto'].items(), key=lambda x: x[1])
    
    recomendacoes = [
        f"PRIORIDADE ALTA: Investir em {principal_projeto[0]} - representa {principal_projeto[1]} chamados",
        f"EFICIÊNCIA: Otimizar processos em {projeto_mais_lento[0]} - tempo médio de {projeto_mais_lento[1]:.1f}h",
        f"AUTOMAÇÃO: {kpis['percentual_alta_prioridade']:.1f}% dos chamados são alta prioridade - implementar triagem automática",
        "CAPACITAÇÃO: Treinar equipe nos tipos de projeto com maior volume",
        "MONITORAMENTO: Implementar alertas para chamados que excedem tempo médio",
        "PREVENÇÃO: Criar base de conhecimento para problemas recorrentes"
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