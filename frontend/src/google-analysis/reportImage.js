const IMAGE_WIDTH = 1080;
const IMAGE_HEIGHT = 1350;
const FONT = 'Inter, Manrope, Arial, sans-serif';

function roundedRect(ctx, x, y, width, height, radius) {
  const safeRadius = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.roundRect(x, y, width, height, safeRadius);
}

function fillRoundedRect(ctx, x, y, width, height, radius, fill) {
  roundedRect(ctx, x, y, width, height, radius);
  ctx.fillStyle = fill;
  ctx.fill();
}

function fitText(ctx, value, maxWidth) {
  const text = String(value ?? '—');
  if (ctx.measureText(text).width <= maxWidth) return text;
  let shortened = text;
  while (shortened.length > 1 && ctx.measureText(`${shortened}…`).width > maxWidth) shortened = shortened.slice(0, -1);
  return `${shortened.trim()}…`;
}

function wrapText(ctx, value, maxWidth, maxLines = 2) {
  const words = String(value || '—').split(/\s+/);
  const lines = [];
  let line = '';
  for (let index = 0; index < words.length; index += 1) {
    const word = words[index];
    const candidate = line ? `${line} ${word}` : word;
    if (ctx.measureText(candidate).width <= maxWidth) {
      line = candidate;
    } else if (lines.length < maxLines - 1) {
      if (line) lines.push(line);
      line = word;
    } else {
      const remaining = [line, ...words.slice(index)].filter(Boolean).join(' ');
      lines.push(fitText(ctx, remaining, maxWidth));
      return lines;
    }
  }
  if (line && lines.length < maxLines) lines.push(line);
  return lines;
}

function drawLabel(ctx, text, x, y, color = '#7d8aa0') {
  ctx.fillStyle = color;
  ctx.font = `700 18px ${FONT}`;
  ctx.letterSpacing = '1px';
  ctx.fillText(String(text).toUpperCase(), x, y);
  ctx.letterSpacing = '0px';
}

function drawFittedText(ctx, value, x, y, maxWidth, { maxSize = 34, minSize = 20, weight = 800, color = '#f5f7fb' } = {}) {
  const text = String(value ?? '—');
  let size = maxSize;
  do {
    ctx.font = `${weight} ${size}px ${FONT}`;
    if (ctx.measureText(text).width <= maxWidth) break;
    size -= 1;
  } while (size > minSize);
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
}

function drawMetric(ctx, { x, y, width, label, value, detail, accent = '#4ed3df' }) {
  fillRoundedRect(ctx, x, y, width, 134, 22, '#121925');
  ctx.fillStyle = accent;
  ctx.fillRect(x, y, 5, 134);
  drawLabel(ctx, label, x + 24, y + 34);
  drawFittedText(ctx, value, x + 24, y + 79, width - 48);
  if (detail) {
    ctx.fillStyle = '#8d99ab';
    ctx.font = `500 18px ${FONT}`;
    ctx.fillText(fitText(ctx, detail, width - 48), x + 24, y + 110);
  }
}

function drawScore(ctx, report, centerX, centerY) {
  const score = report.score_reliable && Number.isFinite(Number(report.score)) ? Number(report.score) : 0;
  ctx.lineWidth = 24;
  ctx.strokeStyle = '#26303d';
  ctx.beginPath();
  ctx.arc(centerX, centerY, 106, 0, Math.PI * 2);
  ctx.stroke();
  const gradient = ctx.createLinearGradient(centerX - 100, centerY, centerX + 100, centerY);
  gradient.addColorStop(0, '#37d6bd');
  gradient.addColorStop(1, '#4ab8ff');
  ctx.strokeStyle = gradient;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.arc(centerX, centerY, 106, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (score / 100));
  ctx.stroke();
  ctx.lineCap = 'butt';
  ctx.textAlign = 'center';
  ctx.fillStyle = '#f7f9fc';
  ctx.font = `900 68px ${FONT}`;
  ctx.fillText(report.score_reliable ? Math.round(score) : '—', centerX, centerY + 15);
  ctx.fillStyle = '#7d8aa0';
  ctx.font = `700 18px ${FONT}`;
  ctx.fillText(report.score_reliable ? 'DE 100' : 'SEM NOTA', centerX, centerY + 53);
  ctx.textAlign = 'left';
}

function ratingText(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(1).replace('.', ',') : '—';
}

function safeFileName(value) {
  return String(value || 'empresa')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'empresa';
}

export function formatMapPosition(value, compact = false) {
  const position = Number(value);
  const isTopTwenty = Number.isInteger(position) && position >= 1 && position <= 20;
  if (!isTopTwenty) return '20+';
  return compact ? `POS. ${position}` : `${position}º lugar`;
}

export function buildGoogleAnalysisImage(report) {
  const canvas = document.createElement('canvas');
  canvas.width = IMAGE_WIDTH;
  canvas.height = IMAGE_HEIGHT;
  const ctx = canvas.getContext('2d');
  const company = report.company || {};
  const competition = report.competition || {};
  const competitors = (competition.competitors || []).slice(0, 5);
  const position = formatMapPosition(competition.position);
  const improvements = Number(report.improvements_count || 0);

  const background = ctx.createLinearGradient(0, 0, IMAGE_WIDTH, IMAGE_HEIGHT);
  background.addColorStop(0, '#0b1018');
  background.addColorStop(.62, '#101722');
  background.addColorStop(1, '#17122b');
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, IMAGE_WIDTH, IMAGE_HEIGHT);

  const glow = ctx.createRadialGradient(900, 260, 20, 900, 260, 520);
  glow.addColorStop(0, 'rgba(89, 59, 219, .32)');
  glow.addColorStop(1, 'rgba(89, 59, 219, 0)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, IMAGE_WIDTH, IMAGE_HEIGHT);

  ctx.fillStyle = '#3ed0c4';
  ctx.font = `800 20px ${FONT}`;
  ctx.letterSpacing = '3px';
  ctx.fillText('RELATÓRIO DA SUA FICHA NO GOOGLE', 64, 68);
  ctx.letterSpacing = '0px';
  if (report.demo) {
    fillRoundedRect(ctx, 822, 36, 194, 44, 22, '#33264f');
    ctx.fillStyle = '#d8c8ff';
    ctx.font = `800 16px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.fillText('DEMONSTRAÇÃO', 919, 64);
    ctx.textAlign = 'left';
  }

  drawScore(ctx, report, 190, 232);
  ctx.fillStyle = '#f7f9fc';
  ctx.font = `900 54px ${FONT}`;
  ctx.fillText(fitText(ctx, company.name, 710), 350, 157);
  ctx.fillStyle = '#9aa6b8';
  ctx.font = `500 22px ${FONT}`;
  const identity = [company.category, company.address].filter(Boolean).join(' · ') || 'Endereço não informado';
  wrapText(ctx, identity, 660, 2).forEach((line, index) => ctx.fillText(line, 350, 201 + index * 31));

  fillRoundedRect(ctx, 350, 276, 666, 82, 18, '#171a24');
  ctx.fillStyle = improvements ? '#ffb7a9' : '#79dfc5';
  ctx.font = `800 22px ${FONT}`;
  const alert = improvements
    ? `A ficha está deixando clientes para a concorrência: ${improvements} ${improvements === 1 ? 'ponto' : 'pontos'} para corrigir.`
    : 'Sua ficha está bem preenchida. Continue fortalecendo avaliações e conteúdo.';
  wrapText(ctx, alert, 618, 2).forEach((line, index) => ctx.fillText(line, 374, 309 + index * 27));

  const metricWidth = 226;
  drawMetric(ctx, { x: 64, y: 402, width: metricWidth, label: 'Nota dos clientes', value: `★ ${ratingText(company.rating)}`, accent: '#f4bf45' });
  drawMetric(ctx, { x: 306, y: 402, width: metricWidth, label: 'Posição no mapa', value: position, accent: '#4ab8ff' });
  drawMetric(ctx, { x: 548, y: 402, width: metricWidth, label: 'Itens pra corrigir', value: `${improvements} de 16`, accent: '#ff7d67' });
  drawMetric(ctx, { x: 790, y: 402, width: metricWidth, label: 'Avaliações', value: String(company.review_count ?? 0), accent: '#a88cff' });

  ctx.fillStyle = '#f4f6fa';
  ctx.font = `900 30px ${FONT}`;
  ctx.fillText('Posição e concorrentes', 64, 600);
  ctx.fillStyle = '#8d99ab';
  ctx.font = `500 19px ${FONT}`;
  ctx.fillText(fitText(ctx, `${competition.keyword || 'Busca local'} · ${competition.location || company.address || 'Localização consultada'}`, 952), 64, 632);

  fillRoundedRect(ctx, 64, 664, 952, 102, 22, '#14212a');
  fillRoundedRect(ctx, 84, 686, 112, 58, 29, '#153e36');
  ctx.fillStyle = '#69e0b4';
  ctx.font = `900 22px ${FONT}`;
  ctx.textAlign = 'center';
  ctx.fillText(formatMapPosition(competition.position, true), 140, 722);
  ctx.textAlign = 'left';
  ctx.fillStyle = '#f5f7fb';
  ctx.font = `800 24px ${FONT}`;
  ctx.fillText(fitText(ctx, company.name, 530), 220, 703);
  ctx.fillStyle = '#94a1b3';
  ctx.font = `500 18px ${FONT}`;
  ctx.fillText(fitText(ctx, company.address || 'Endereço não informado', 530), 220, 734);
  ctx.fillStyle = '#f4bf45';
  ctx.font = `800 20px ${FONT}`;
  ctx.fillText(`★ ${ratingText(company.rating)}  ·  ${company.review_count ?? 0} avaliações`, 790, 720);

  const rowHeight = 94;
  competitors.forEach((item, index) => {
    const y = 786 + index * rowHeight;
    fillRoundedRect(ctx, 64, y, 952, 80, 18, index % 2 ? '#111823' : '#121b27');
    fillRoundedRect(ctx, 84, y + 15, 96, 50, 25, '#202b39');
    ctx.fillStyle = '#8ad9c1';
    ctx.font = `900 18px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.fillText(`POS. ${item.position ?? '—'}`, 132, y + 47);
    ctx.textAlign = 'left';
    ctx.fillStyle = '#f1f4f8';
    ctx.font = `800 21px ${FONT}`;
    ctx.fillText(fitText(ctx, item.name || 'Concorrente', 490), 204, y + 34);
    ctx.fillStyle = '#8592a5';
    ctx.font = `500 17px ${FONT}`;
    const detail = [item.category, item.address].filter(Boolean).join(' · ') || 'Perfil concorrente na busca local';
    ctx.fillText(fitText(ctx, detail, 490), 204, y + 60);
    ctx.fillStyle = '#f4bf45';
    ctx.font = `800 18px ${FONT}`;
    ctx.fillText(`★ ${ratingText(item.rating)}`, 764, y + 34);
    ctx.fillStyle = '#9aa6b8';
    ctx.font = `600 17px ${FONT}`;
    ctx.fillText(`${item.review_count ?? 0} avaliações`, 764, y + 60);
  });

  if (!competitors.length) {
    fillRoundedRect(ctx, 64, 786, 952, 112, 18, '#111823');
    ctx.fillStyle = '#94a1b3';
    ctx.font = `600 20px ${FONT}`;
    ctx.fillText('Não foi possível listar concorrentes nesta consulta.', 92, 850);
  }

  ctx.textAlign = 'right';
  ctx.fillStyle = '#4ed3c5';
  ctx.font = `800 17px ${FONT}`;
  ctx.fillText('Dz7 Marketing', 1016, 1310);
  ctx.textAlign = 'left';

  return canvas;
}

export async function downloadGoogleAnalysisImage(report) {
  if (document.fonts?.ready) await document.fonts.ready;
  const canvas = buildGoogleAnalysisImage(report);
  const blob = await new Promise((resolve, reject) => {
    canvas.toBlob((result) => result ? resolve(result) : reject(new Error('Não foi possível criar a imagem.')), 'image/png', 1);
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `analise-google-${safeFileName(report.company?.name)}.png`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
