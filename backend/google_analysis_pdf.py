from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_report_pdf(report: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Análise Google - {report['company']['name']}",
        author="ProspectSites",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Brand", parent=styles["Title"], textColor=colors.HexColor("#176B45"), fontSize=23, leading=27, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], textColor=colors.HexColor("#163C2A"), fontSize=15, leading=19, spaceBefore=12, spaceAfter=7))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], textColor=colors.HexColor("#66756D"), fontSize=8.5, leading=12))
    styles.add(ParagraphStyle(name="Score", parent=styles["Title"], textColor=colors.HexColor("#176B45"), fontSize=35, leading=39, alignment=TA_CENTER))

    company = report["company"]
    score = report.get("score")
    score_label = f"{score}/100" if report.get("score_reliable") and score is not None else "Dados insuficientes"
    story = [
        Paragraph("ProspectSites", styles["Brand"]),
        Paragraph("Diagnóstico de Perfil da Empresa no Google", styles["Heading1"]),
        Paragraph(company["name"], styles["Heading2"]),
        Paragraph(f"Coleta: {report['collected_at']} · Metodologia {report['methodology_version']}", styles["Small"]),
        Spacer(1, 8 * mm),
        Paragraph(score_label, styles["Score"]),
        Paragraph(f"Cobertura: {report['coverage']:.0f}% dos pesos da metodologia", ParagraphStyle(name="CenterSmall", parent=styles["Small"], alignment=TA_CENTER)),
        Paragraph(report["summary"], styles["BodyText"]),
        Paragraph("Prioridades", styles["Section"]),
    ]

    if report.get("priorities"):
        for index, priority in enumerate(report["priorities"], start=1):
            story.extend([
                Paragraph(f"{index}. {priority['title']}", styles["Heading3"]),
                Paragraph(priority["reason"], styles["BodyText"]),
                Paragraph(f"Ação recomendada: {priority['action']}", styles["Small"]),
            ])
    else:
        story.append(Paragraph("Nenhuma prioridade confirmada nos dados avaliáveis.", styles["BodyText"]))

    story.extend([Paragraph("Checklist dos 16 itens", styles["Section"])])
    rows = [["Item", "Estado", "Evidência"]]
    for item in report.get("checklist", []):
        rows.append([
            Paragraph(item["label"], styles["Small"]),
            Paragraph(item["state_label"], styles["Small"]),
            Paragraph(str(item["evidence"]), styles["Small"]),
        ])
    table = Table(rows, colWidths=[42 * mm, 35 * mm, 100 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#176B45")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DCE8E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F8F5")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([table, Paragraph("Comparação competitiva", styles["Section"])])

    competition = report.get("competition") or {}
    position = competition.get("position")
    position_text = f"Posição observada: {position}º" if position else f"Não encontrada entre os {competition.get('depth', 0)} resultados consultados"
    story.extend([
        Paragraph(f"Palavra-chave: {competition.get('keyword', 'Não informada')}", styles["BodyText"]),
        Paragraph(f"Localização: {competition.get('location', 'Não informada')} · {position_text}", styles["BodyText"]),
        Paragraph(f"Amostra: {competition.get('sample_size', 0)} · Mediana de avaliações: {competition.get('median_review_count', '—')}", styles["BodyText"]),
    ])
    competitor_rows = [["Posição", "Empresa", "Nota", "Avaliações"]]
    for entry in competition.get("competitors", []):
        competitor_rows.append([entry.get("position", "—"), entry.get("name", "—"), entry.get("rating", "—"), entry.get("review_count", "—")])
    competitor_table = Table(competitor_rows, colWidths=[25 * mm, 90 * mm, 25 * mm, 35 * mm], repeatRows=1)
    competitor_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF6F0")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DCE8E1")),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([competitor_table, Paragraph("Metodologia e limitações", styles["Section"]), Paragraph("A Nota ProspectSites é própria, determinística e normalizada somente sobre itens efetivamente avaliáveis. Ela não representa uma nota do Google nem revela fatores oficiais de ranqueamento.", styles["BodyText"])])
    for limitation in report.get("limitations", []):
        story.append(Paragraph(f"• {limitation}", styles["Small"]))
    if report.get("demo"):
        story.append(Paragraph("DOCUMENTO DE DEMONSTRAÇÃO — DADOS FICTÍCIOS", ParagraphStyle(name="Demo", parent=styles["Heading2"], textColor=colors.HexColor("#B45309"), alignment=TA_CENTER, spaceBefore=18)))

    doc.build(story)
    return buffer.getvalue()
