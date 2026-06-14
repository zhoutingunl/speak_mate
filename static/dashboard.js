'use strict';
const $ = (id) => document.getElementById(id);
const DIMS = [['pronunciation', '发音'], ['fluency', '流利'], ['grammar', '语法'],
              ['vocabulary', '词汇'], ['expression', '表达'], ['communication', '沟通']];
const CAT_CN = { grammar: '语法', expression: '表达', tense: '时态',
                 article: '冠词', preposition: '介词', agreement: '主谓一致' };

load();
async function load() {
  fetch('/api/track', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event: 'dashboard_open' }),
  }).catch(() => {});
  const d = await fetch('/api/dashboard').then(r => r.json());
  renderStats(d);
  renderRadar(d.current_skill);
  renderGrowth(d.growth);
  renderCoverage(d.scenario_coverage);
  renderErrors(d.error_stats);
}

function renderStats(d) {
  const cards = [
    ['练习次数', d.practice_count],
    ['训练时长', d.total_minutes + ' 分'],
    ['连续打卡', d.streak + ' 天'],
    ['场景覆盖', `${d.covered_scenarios}/${d.total_scenarios}`],
  ];
  $('stats').innerHTML = cards.map(([k, v]) =>
    `<div class="stat"><div class="sv">${v}</div><div class="sk">${k}</div></div>`).join('');
}

// ---- 六维雷达(纯 SVG)----
function renderRadar(skill) {
  const W = 320, C = W / 2, R = 110, n = DIMS.length;
  const ang = (i) => -Math.PI / 2 + i * 2 * Math.PI / n;
  const pt = (i, r) => [C + r * Math.cos(ang(i)), C + r * Math.sin(ang(i))];
  let svg = `<svg viewBox="0 0 ${W} ${W}" width="100%" height="320">`;
  // 网格
  for (const g of [0.25, 0.5, 0.75, 1]) {
    const poly = DIMS.map((_, i) => pt(i, R * g).join(',')).join(' ');
    svg += `<polygon points="${poly}" fill="none" stroke="#2e3654"/>`;
  }
  // 轴 + 标签
  let missing = false;
  DIMS.forEach(([key, label], i) => {
    const [x, y] = pt(i, R);
    svg += `<line x1="${C}" y1="${C}" x2="${x}" y2="${y}" stroke="#2e3654"/>`;
    const [lx, ly] = pt(i, R + 22);
    const v = skill[key];
    if (v == null) missing = true;
    svg += `<text x="${lx}" y="${ly}" fill="#98a0bd" font-size="12" text-anchor="middle" dominant-baseline="middle">${label}${v == null ? '' : ' ' + v}</text>`;
  });
  // 数据多边形(None 当 0 画,并提示)
  const dataPoly = DIMS.map(([key], i) =>
    pt(i, R * ((skill[key] == null ? 0 : skill[key]) / 100)).join(',')).join(' ');
  svg += `<polygon points="${dataPoly}" fill="rgba(108,140,255,.35)" stroke="#6c8cff" stroke-width="2"/>`;
  svg += '</svg>';
  $('radar').innerHTML = svg;
  $('radarNote').textContent = missing
    ? '发音/流利需语音数据,练习后填充;灰显维度本期暂无数据' : '';
}

// ---- 成长曲线(综合分)----
function renderGrowth(growth) {
  const pts = growth.filter(g => g.overall != null);
  if (pts.length < 2) {
    $('growth').innerHTML = '<p class="na">至少完成 2 次训练后显示趋势</p>';
    return;
  }
  const W = 360, H = 200, pad = 28;
  const xs = (i) => pad + i * (W - 2 * pad) / (pts.length - 1);
  const ys = (v) => H - pad - (v / 100) * (H - 2 * pad);
  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="200">`;
  for (const g of [0, 25, 50, 75, 100]) {
    svg += `<line x1="${pad}" y1="${ys(g)}" x2="${W - pad}" y2="${ys(g)}" stroke="#2e3654"/>`;
    svg += `<text x="4" y="${ys(g) + 4}" fill="#98a0bd" font-size="10">${g}</text>`;
  }
  const line = pts.map((g, i) => `${xs(i)},${ys(g.overall)}`).join(' ');
  svg += `<polyline points="${line}" fill="none" stroke="#46d39a" stroke-width="2"/>`;
  pts.forEach((g, i) => { svg += `<circle cx="${xs(i)}" cy="${ys(g.overall)}" r="3" fill="#46d39a"/>`; });
  svg += '</svg>';
  $('growth').innerHTML = svg;
  $('growthNote').textContent = `共 ${pts.length} 次,最新综合分 ${pts[pts.length - 1].overall}`;
}

function renderCoverage(cov) {
  const max = Math.max(1, ...cov.map(c => c.count));
  $('coverage').innerHTML = cov.map(c =>
    `<div class="bar-row"><span class="k">${c.name}</span>
       <div class="bar"><i style="width:${c.count / max * 100}%"></i></div>
       <span class="v">${c.count}</span></div>`).join('') || '<p class="na">暂无</p>';
}

function renderErrors(errs) {
  if (!errs.length) { $('errors').innerHTML = '<p class="na">暂无纠错记录</p>'; return; }
  const max = Math.max(...errs.map(e => e.count));
  $('errors').innerHTML = errs.map(e =>
    `<div class="bar-row"><span class="k">${CAT_CN[e.category] || e.category}</span>
       <div class="bar"><i style="width:${e.count / max * 100}%"></i></div>
       <span class="v">${e.count}</span></div>`).join('');
}
