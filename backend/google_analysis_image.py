"""Render a compact, shareable analysis image without a browser."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont


def _font(size: int, bold: bool = False):
    names = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for name in names:
        if Path(name).is_file():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def render_analysis_png(report: dict) -> bytes:
    image = Image.new("RGB", (1080, 1350), "#0d131e")
    draw = ImageDraw.Draw(image)
    white, muted, accent = "#f5f7fb", "#a5b2c4", "#56dec5"
    company = report.get("company") or {}
    competition = report.get("competition") or {}

    def line(text: str, y: int, size: int = 24, color: str = white, bold: bool = False, width: int = 62, max_lines: int = 2):
        for index, item in enumerate(textwrap.wrap(str(text or "—"), width=width, max_lines=max_lines, placeholder="…") or ["—"]):
            draw.text((64, y + index * (size + 9)), item, fill=color, font=_font(size, bold))

    line("RELATÓRIO DA SUA FICHA NO GOOGLE", 58, 22, accent, True)
    if report.get("demo"):
        line("DEMONSTRAÇÃO", 100, 20, "#ffcc83", True)
    line(company.get("name") or "Empresa não informada", 165, 48, white, True, 31, 2)
    line(" · ".join(str(x) for x in (company.get("category"), company.get("address")) if x) or "Endereço não informado", 305, 21, muted, False, 76, 3)
    draw.rounded_rectangle((64, 420, 1016, 595), radius=24, fill="#182433")
    score = report.get("score")
    score_text = f"{round(float(score))}/100" if report.get("score_reliable") and score is not None else "Sem nota confiável"
    line("PONTUAÇÃO DA FICHA", 450, 20, accent, True)
    line(score_text, 492, 42, white, True)
    coverage = report.get("coverage")
    line(f"Cobertura dos dados: {coverage}%" if coverage is not None else "Cobertura não informada", 620, 22, muted)
    rating = company.get("rating")
    reviews = company.get("review_count")
    line(f"Avaliação dos clientes: {rating if rating is not None else 'não informada'}  |  Avaliações: {reviews if reviews is not None else 'não informadas'}", 690, 22)
    position = competition.get("position")
    line(f"Posição na busca consultada: {str(position) + 'º lugar' if position is not None else 'não identificada'}", 744, 22)
    line("PONTOS PRIORITÁRIOS", 830, 22, accent, True)
    priorities = report.get("priorities") or []
    for index, item in enumerate(priorities[:3]):
        value = item if isinstance(item, str) else item.get("title") or item.get("label") or item.get("action") or item.get("name")
        line(f"{index + 1}. {value or 'Consultar relatório completo'}", 875 + index * 73, 21, white, False, 74, 2)
    if not priorities:
        line("Consulte o relatório completo para os detalhes.", 885, 21, muted)
    line("Os resultados refletem os dados disponíveis na consulta.", 1220, 18, muted)
    line("Dz7 Marketing", 1270, 20, accent, True)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
