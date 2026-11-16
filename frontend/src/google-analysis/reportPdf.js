import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";

const COLORS = {
  ink: [20, 27, 39],
  muted: [93, 105, 124],
  teal: [20, 184, 166],
  blue: [56, 189, 248],
  line: [222, 228, 236],
  pale: [245, 248, 252],
  white: [255, 255, 255],
};

function safeFileName(value = "empresa") {
  return String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase() || "empresa";
}

function valueText(value) {
  if (value === null || value === undefined || value === "") return "Não informado";
  if (Array.isArray(value)) return value.map(valueText).join("; ");
  if (typeof value === "object") {
    return Object.entries(value).map(([key, item]) => `${key}: ${valueText(item)}`).join("; ");
  }
  return String(value);
}

function positionText(position) {
  const number = Number(position);
  return Number.isFinite(number) && number > 0 && number <= 20 ? `${number}º lugar` : "20+";
}

function ensureSpace(doc, y, needed = 20) {
  if (y + needed <= 280) return y;
  doc.addPage();
  return 18;
}

function sectionTitle(doc, title, y) {
  const nextY = ensureSpace(doc, y, 16);
  doc.setFillColor(...COLORS.teal);
  doc.roundedRect(14, nextY - 5, 4, 9, 2, 2, "F");
  doc.setTextColor(...COLORS.ink);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  doc.text(title, 22, nextY + 2);
  return nextY + 9;
}

function paragraph(doc, text, y, options = {}) {
  const width = options.width || 182;
  const size = options.size || 9.5;
  const color = options.color || COLORS.muted;
  const lines = doc.splitTextToSize(valueText(text), width);
  let cursor = y;
  doc.setFont("helvetica", options.bold ? "bold" : "normal");
  doc.setFontSize(size);
  doc.setTextColor(...color);
  lines.forEach((line) => {
    cursor = ensureSpace(doc, cursor, 7);
    doc.text(line, 14, cursor);
    cursor += 5;
  });
  return cursor;
}

function table(doc, config) {
  autoTable(doc, {
    margin: { left: 14, right: 14 },
    theme: "grid",
    styles: { font: "helvetica", fontSize: 7.5, cellPadding: 2.2, textColor: COLORS.ink, lineColor: COLORS.line, lineWidth: 0.2, overflow: "linebreak" },
    headStyles: { fillColor: COLORS.ink, textColor: COLORS.white, fontStyle: "bold" },
    alternateRowStyles: { fillColor: COLORS.pale },
    ...config,
  });
  return doc.lastAutoTable.finalY + 8;
}

export function buildGoogleAnalysisPdf(report) {
  const company = report.company || {};
  const competition = report.competition || {};
  const doc = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait" });
  doc.setProperties({
    title: `Análise Google - ${company.name || "Empresa"}`,
    subject: "Diagnóstico completo do Perfil da Empresa no Google",
    author: "Dz7 Marketing",
  });

  doc.setFillColor(...COLORS.ink);
  doc.rect(0, 0, 210, 58, "F");
  doc.setFillColor(...COLORS.teal);
  doc.rect(0, 0, 5, 58, "F");
  doc.setTextColor(...COLORS.teal);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.text("RELATÓRIO DA SUA FICHA NO GOOGLE", 14, 14);
  doc.setTextColor(...COLORS.white);
  doc.setFontSize(22);
  doc.text(doc.splitTextToSize(company.name || "Empresa", 145), 14, 27);
  doc.setTextColor(190, 201, 216);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.text(doc.splitTextToSize(`${company.category || "Categoria não informada"} · ${company.address || "Endereço não informado"}`, 145), 14, 40);
  doc.setTextColor(...COLORS.white);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(25);
  doc.text(report.score_reliable ? String(Math.round(report.score || 0)) : "—", 181, 27, { align: "center" });
  doc.setFontSize(8);
  doc.text(report.score_reliable ? "DE 100" : "SEM NOTA", 181, 34, { align: "center" });
  doc.setTextColor(190, 201, 216);
  doc.setFont("helvetica", "normal");
  doc.text(new Date(report.collected_at).toLocaleString("pt-BR"), 196, 50, { align: "right" });

  let y = 66;
  y = table(doc, {
    startY: y,
    head: [["Nota dos clientes", "Posição no mapa", "Itens para corrigir", "Avaliações", "Cobertura"]],
    body: [[
      company.rating ?? "—",
      positionText(competition.position),
      `${report.improvements_count || 0} de 16`,
      company.review_count ?? 0,
      `${Math.round(report.coverage || 0)}%`,
    ]],
    styles: { fontSize: 8.5, cellPadding: 3, halign: "center" },
  });

  y = sectionTitle(doc, "Resumo executivo", y);
  y = paragraph(doc, report.summary, y);
  y = paragraph(doc, `Metodologia ${report.methodology_version} · cobertura mínima confiável: ${report.minimum_coverage}% · resultado: ${report.score_reliable ? "confiável" : "parcial"}.`, y + 1, { size: 8 });

  y = sectionTitle(doc, "Melhorias prioritárias", y + 4);
  const priorities = report.priorities || [];
  if (priorities.length) {
    y = table(doc, {
      startY: y,
      head: [["Prioridade", "Motivo", "Ação recomendada"]],
      body: priorities.map((item) => [item.title, item.reason, item.action]),
      columnStyles: { 0: { cellWidth: 35 }, 1: { cellWidth: 70 }, 2: { cellWidth: 77 } },
    });
  } else {
    y = paragraph(doc, "Nenhuma melhoria confirmada nos dados avaliáveis.", y);
  }

  y = sectionTitle(doc, "Checklist completo", y);
  y = table(doc, {
    startY: y,
    head: [["Item", "Situação", "Pontos", "Evidência", "Ação recomendada", "Fonte"]],
    body: (report.checklist || []).map((item) => [
      item.label,
      item.state_label,
      item.points === null ? "—" : `${item.points}/${item.weight}`,
      item.evidence,
      item.action,
      item.source,
    ]),
    columnStyles: {
      0: { cellWidth: 27 }, 1: { cellWidth: 24 }, 2: { cellWidth: 17 },
      3: { cellWidth: 43 }, 4: { cellWidth: 48 }, 5: { cellWidth: 23 },
    },
  });

  y = sectionTitle(doc, "Posição e comparação competitiva", y);
  y = paragraph(doc, `${competition.keyword || "Palavra-chave não informada"} · ${competition.location || "Localização não informada"}`, y, { bold: true, color: COLORS.ink });
  y = paragraph(doc, `Posição observada: ${positionText(competition.position)} · amostra: ${competition.sample_size ?? 0} · mediana de avaliações: ${competition.median_review_count ?? "não disponível"}.`, y, { size: 8.5 });
  const competitors = competition.competitors || [];
  if (competitors.length) {
    y = table(doc, {
      startY: y + 2,
      head: [["Posição", "Concorrente", "Endereço", "Nota", "Avaliações"]],
      body: competitors.map((item) => [item.position ? `${item.position}º` : "—", item.name, item.address || "Não informado", item.rating ?? "—", item.review_count ?? 0]),
      columnStyles: { 0: { cellWidth: 18 }, 1: { cellWidth: 46 }, 2: { cellWidth: 78 }, 3: { cellWidth: 18 }, 4: { cellWidth: 22 } },
    });
  } else {
    y = paragraph(doc, "Não foi possível listar concorrentes nesta consulta.", y + 2);
  }

  y = sectionTitle(doc, "Consumo estimado", y);
  y = paragraph(doc, `${report.cost?.searches_used ?? 0} busca(s) · custo estimado de US$ ${Number(report.cost?.estimated_usd || 0).toFixed(3)}. ${report.cost?.basis || ""}`, y);

  y = sectionTitle(doc, "Fontes e limitações", y + 3);
  const sources = [...new Set((report.checklist || []).map((item) => item.source).filter(Boolean))];
  y = paragraph(doc, `Fontes utilizadas: ${sources.length ? sources.join("; ") : "não informadas"}.`, y, { bold: true, color: COLORS.ink });
  (report.limitations || []).forEach((item) => {
    y = paragraph(doc, `• ${item}`, y + 1);
  });
  y = paragraph(doc, "A Nota ProspectSites é própria e não representa uma nota do Google. Os pesos não são fatores oficiais de ranqueamento.", y + 3, { bold: true, color: COLORS.ink });

  const pages = doc.getNumberOfPages();
  for (let page = 1; page <= pages; page += 1) {
    doc.setPage(page);
    doc.setDrawColor(...COLORS.line);
    doc.line(14, 289, 196, 289);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(7.5);
    doc.setTextColor(...COLORS.muted);
    doc.text("Dz7 Marketing · relatório gerado localmente e não salvo no banco", 14, 294);
    doc.text(`${page}/${pages}`, 196, 294, { align: "right" });
  }
  return doc;
}

export function downloadGoogleAnalysisPdf(report) {
  const doc = buildGoogleAnalysisPdf(report);
  doc.save(`analise-google-completa-${safeFileName(report.company?.name)}.pdf`);
}
