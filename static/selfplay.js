'use strict';
const $ = (id) => document.getElementById(id);
let es = null;

init();
async function init() {
  const scenarios = await fetch('/api/scenarios').then(r => r.json());
  $('scenario').innerHTML = scenarios
    .map(s => `<option value="${s.key}">${s.name}</option>`).join('');

  const { voices } = await fetch('/api/voices').then(r => r.json());
  const opts = voices.map(v => `<option value="${v.id}">${v.name}</option>`).join('');
  $('tutorVoice').innerHTML = opts;
  $('learnerVoice').innerHTML = opts;
  $('tutorVoice').value = 'English_Trustworthy_Man';
  $('learnerVoice').value = 'English_Graceful_Lady';

  $('runBtn').onclick = run;
}

// ---- 朗读队列(串行播放,避免重叠)----
const audio = { queue: [], playing: false, cur: null };
function enqueueSpeak(text, voice) {
  if (!$('speak').checked) return;
  audio.queue.push({ text, voice });
  pump();
}
function pump() {
  if (audio.playing || !audio.queue.length) return;
  audio.playing = true;
  const { text, voice } = audio.queue.shift();
  const a = new Audio('/api/tts?text=' + encodeURIComponent(text) +
    '&voice=' + encodeURIComponent(voice));
  audio.cur = a;
  const next = () => { audio.playing = false; audio.cur = null; pump(); };
  a.onended = next; a.onerror = next;
  a.play().catch(next);
}
function stopSpeak() {
  audio.queue = [];
  if (audio.cur) { try { audio.cur.pause(); } catch (e) {} audio.cur = null; }
  audio.playing = false;
}

function run() {
  if (es) es.close();
  stopSpeak();
  $('stage').innerHTML = '';
  $('summary').innerHTML = '';
  $('runBtn').disabled = true;
  $('runBtn').textContent = '对弈中…';

  const q = new URLSearchParams({
    scenario: $('scenario').value, level: $('level').value,
    difficulty: $('difficulty').value, turns: $('turns').value,
  });
  fetch('/api/track', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event: 'selfplay_run', payload: { scenario: $('scenario').value } }),
  }).catch(() => {});
  es = new EventSource('/api/selfplay?' + q.toString());
  es.onmessage = (e) => handle(JSON.parse(e.data));
  es.onerror = () => finish();
}

function finish() {
  if (es) { es.close(); es = null; }
  $('runBtn').disabled = false;
  $('runBtn').textContent = '重新开始';
}

let lastLearner = null;  // 纠错卡片挂到上一条学习者气泡后

function handle(ev) {
  switch (ev.type) {
    case 'tutor':
      bubble('ai', '🎙️ ' + ev.text); lastLearner = null;
      enqueueSpeak(ev.text, $('tutorVoice').value); break;
    case 'learner':
      lastLearner = bubble('me', '🧑 ' + ev.text);
      enqueueSpeak(ev.text, $('learnerVoice').value); break;
    case 'correction':
      renderCorrection(ev); break;
    case 'summary':
      renderSummary(ev); break;
    case 'judge':
      renderJudge(ev.verdict); break;
    case 'error':
      bubble('ai', '⚠️ ' + ev.msg); finish(); break;
    case 'done':
      finish(); break;
  }
}

function bubble(who, text) {
  const b = document.createElement('div');
  b.className = 'bubble ' + (who === 'me' ? 'me' : 'ai');
  b.textContent = text;
  $('stage').appendChild(b);
  b.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return b;
}

function renderCorrection(ev) {
  const c = document.createElement('div');
  c.className = 'feedback';
  const fixes = ev.items.map(x =>
    `<div class="fix"><span class="old">${x.original}</span> → <span class="new">${x.corrected}</span><div class="lbl">${x.reason}</div></div>`
  ).join('');
  c.innerHTML = `<div class="card"><span class="lbl">表达优化</span>${fixes}` +
    (ev.polished ? `<div class="fix">建议:<span class="new">${ev.polished}</span></div>` : '') +
    `</div>`;
  $('stage').appendChild(c);
  c.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function renderSummary(ev) {
  const sk = ev.raw_skills || {};
  const dims = [['grammar', '语法'], ['vocabulary', '词汇'],
                ['expression', '表达'], ['communication', '沟通']];
  const bars = dims.map(([k, label]) => {
    const v = sk[k];
    if (v == null) return '';
    return `<div class="bar-row"><span class="k">${label}</span><div class="bar"><i style="width:${v}%"></i></div><span class="v">${v}</span></div>`;
  }).join('');
  const list = (a) => (a && a.length) ? `<ul class="tight">${a.map(x => `<li>${x}</li>`).join('')}</ul>` : '<p class="na">—</p>';
  $('summary').innerHTML = `
    <h2>📊 课后总结</h2>
    <div class="bars">${bars}</div>
    <p class="na">发音/流利无真实人声,故不计入</p>
    <h3>✨ 优秀表达</h3>${list(ev.highlights)}
    <h3>⚠️ 高频错误</h3>${list(ev.frequent_errors)}
    <h3>💡 推荐表达</h3>${list(ev.recommended)}
    <h3>📌 训练建议</h3><div class="advice">${ev.advice || '—'}</div>`;
}

function renderJudge(v) {
  if (!v) return;
  const div = document.createElement('div');
  div.className = 'card';
  div.style.marginTop = '14px';
  div.innerHTML = `<span class="lbl">评委评分</span>
    <div class="score-row">
      <span class="score">自然度 <span class="n">${v.naturalness ?? '?'}</span>/5</span>
      <span class="score">考官在角色 <span class="n">${v.tutor_in_role ?? '?'}</span>/5</span>
    </div>
    <div class="lbl">${v.comment || ''}</div>`;
  $('summary').appendChild(div);
}
