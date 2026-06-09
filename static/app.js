'use strict';

const $ = (id) => document.getElementById(id);
const state = { scenario: null, sessionId: null, recog: null, recorder: null,
                chunks: [], transcript: '', blob: null, recogDone: false,
                recDone: false, pronLive: false };

const DIFF_LABELS = { 1: 'L1 · 入门', 2: 'L2 · 日常', 3: 'L3 · 自然',
                      4: 'L4 · 进阶', 5: 'L5 · 母语级' };

// ---------- 启动 ----------
init();
async function init() {
  const st = await fetch('/api/status').then(r => r.json()).catch(() => ({}));
  state.pronLive = !!st.pron_live;
  $('status').innerHTML =
    `对话 <b class="${st.llm_live ? 'ok' : 'off'}">${st.llm_live ? '在线' : 'Mock'}</b> · ` +
    `发音评测 <b class="${st.pron_live ? 'ok' : 'off'}">${st.pron_live ? '在线' : '降级'}</b>`;

  const scenarios = await fetch('/api/scenarios').then(r => r.json());
  const grid = $('scenarioList');
  scenarios.forEach(sc => {
    const el = document.createElement('div');
    el.className = 'scenario';
    el.innerHTML = `<div class="name">${sc.name}</div><div class="goal">${sc.goal}</div>`;
    el.onclick = () => {
      document.querySelectorAll('.scenario').forEach(n => n.classList.remove('sel'));
      el.classList.add('sel');
      state.scenario = sc;
      $('startBtn').disabled = false;
    };
    grid.appendChild(el);
  });

  $('difficulty').oninput = (e) => $('difficultyLabel').textContent = DIFF_LABELS[e.target.value];
  $('startBtn').onclick = startSession;
  $('endBtn').onclick = endSession;
  $('restartBtn').onclick = () => location.reload();
  setupMic();
}

// ---------- 会话 ----------
async function startSession() {
  const res = await fetch('/api/session', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario: state.scenario.key,
                           difficulty: Number($('difficulty').value) }),
  }).then(r => r.json());
  if (res.error) { alert(res.error); return; }

  state.sessionId = res.session_id;
  $('chatScenario').textContent = '🎬 ' + state.scenario.name;
  $('setup').classList.add('hidden');
  $('chat').classList.remove('hidden');
  $('messages').innerHTML = '';
  addBubble('ai', res.opening);
  playTTS(res.opening);
}

async function endSession() {
  $('chat').classList.add('hidden');
  $('summary').classList.remove('hidden');
  $('summaryBody').innerHTML = '<p class="na">正在生成总结…</p>';
  const r = await fetch('/api/report', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: state.sessionId }),
  }).then(r => r.json());
  renderSummary(r);
}

// ---------- 麦克风:Web Speech API(ASR)+ MediaRecorder(给 Azure) ----------
function setupMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { $('micHint').textContent = '此浏览器不支持语音识别,请用 Chrome'; }

  const btn = $('micBtn');
  const start = (e) => { e.preventDefault(); beginTurn(); };
  const stop = (e) => { e.preventDefault(); finishTurn(); };
  btn.addEventListener('pointerdown', start);
  btn.addEventListener('pointerup', stop);
  btn.addEventListener('pointerleave', stop);
}

async function beginTurn() {
  const btn = $('micBtn');
  btn.classList.add('rec'); btn.textContent = '松开结束';
  state.transcript = ''; state.blob = null; state.chunks = [];
  state.recogDone = false; state.recDone = false;

  // ASR
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SR) {
    const recog = new SR();
    recog.lang = 'en-US'; recog.interimResults = true; recog.continuous = true;
    recog.onresult = (ev) => {
      let t = '';
      for (const r of ev.results) t += r[0].transcript;
      state.transcript = t.trim();
    };
    recog.onend = () => { state.recogDone = true; maybeProcess(); };
    recog.onerror = () => { state.recogDone = true; maybeProcess(); };
    state.recog = recog; recog.start();
  } else { state.recogDone = true; }

  // 录音(给 Azure 评测)
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const rec = new MediaRecorder(stream);
    rec.ondataavailable = (e) => state.chunks.push(e.data);
    rec.onstop = () => {
      state.blob = new Blob(state.chunks, { type: rec.mimeType });
      stream.getTracks().forEach(t => t.stop());
      state.recDone = true; maybeProcess();
    };
    state.recorder = rec; rec.start();
  } catch (err) { state.recDone = true; }
}

function finishTurn() {
  const btn = $('micBtn');
  btn.classList.remove('rec'); btn.textContent = '按住说话';
  try { state.recog && state.recog.stop(); } catch (e) { state.recogDone = true; }
  try { state.recorder && state.recorder.state !== 'inactive' && state.recorder.stop(); }
  catch (e) { state.recDone = true; }
}

let _processed = false;
function maybeProcess() {
  if (!(state.recogDone && state.recDone)) return;
  if (_processed) return; _processed = true;
  setTimeout(() => { _processed = false; }, 100);
  const text = state.transcript;
  if (!text) { return; }
  processTurn(text, state.blob);
}

// ---------- 处理一轮 ----------
async function processTurn(text, blob) {
  addBubble('me', text);
  const fb = document.createElement('div');
  fb.className = 'feedback';
  $('messages').appendChild(fb);

  // 1) 流式回复
  const aiBubble = addBubble('ai', '');
  let reply = '';
  await streamChat(text, (delta) => { reply += delta; aiBubble.textContent = reply; scrollDown(); });
  if (reply) playTTS(reply);

  // 2) 发音评测(旁路,不阻塞对话)
  if (blob && state.pronLive) renderPron(fb, text, blob);
  // 3) 延迟纠错
  renderCorrection(fb, text);
}

function streamChat(text, onDelta) {
  return fetch('/api/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: state.sessionId, text }),
  }).then(async (resp) => {
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split('\n\n'); buf = parts.pop();
      for (const p of parts) {
        const line = p.split('\n').find(l => l.startsWith('data:'));
        if (!line) continue;
        const evt = JSON.parse(line.slice(5).trim());
        if (evt.delta) onDelta(evt.delta);
      }
    }
  });
}

async function renderPron(container, refText, blob) {
  const note = document.createElement('div');
  note.className = 'card'; note.innerHTML = '<span class="lbl">发音评测中…</span>';
  container.appendChild(note);
  const fd = new FormData();
  fd.append('audio', blob, 'rec.webm'); fd.append('ref_text', refText);
  try {
    const s = await fetch('/api/pronounce', { method: 'POST', body: fd }).then(r => r.json());
    if (s.error) { note.remove(); return; }
    note.innerHTML =
      `<span class="lbl">发音评测${s.degraded ? ' <span class="degraded">(降级·仅供参考)</span>' : ''}</span>
       <div class="score-row">
         <span class="score">总分 <span class="n">${s.overall}</span></span>
         <span>发音 ${fmt(s.pronunciation)}</span>
         <span>流利 ${fmt(s.fluency)}</span>
         <span>韵律 ${fmt(s.prosody)}</span>
         <span>完整 ${fmt(s.completeness)}</span>
       </div>`;
  } catch (e) { note.remove(); }
}

async function renderCorrection(container, text) {
  const r = await fetch('/api/correct', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: state.sessionId, text }),
  }).then(r => r.json()).catch(() => null);
  if (!r || !r.has_issues) return;
  const c = document.createElement('div');
  c.className = 'card';
  const fixes = r.corrections.map(x =>
    `<div class="fix"><span class="old">${x.original}</span> → <span class="new">${x.corrected}</span><div class="lbl">${x.reason}</div></div>`
  ).join('');
  c.innerHTML = `<span class="lbl">表达优化${r.degraded ? ' <span class="degraded">(规则)</span>' : ''}</span>${fixes}` +
    (r.polished ? `<div class="fix">建议:<span class="new">${r.polished}</span></div>` : '');
  container.appendChild(c);
}

// ---------- 总结 ----------
function renderSummary(r) {
  const sk = r.raw_skills || {};
  const dims = [['pronunciation', '发音'], ['fluency', '流利'], ['grammar', '语法'],
                ['vocabulary', '词汇'], ['expression', '表达'], ['communication', '沟通']];
  const bars = dims.map(([k, label]) => {
    const v = sk[k];
    if (v == null) return `<div class="bar-row"><span class="k">${label}</span><span class="na">本次无数据</span></div>`;
    return `<div class="bar-row"><span class="k">${label}</span><div class="bar"><i style="width:${v}%"></i></div><span class="v">${v}</span></div>`;
  }).join('');
  const list = (arr) => (arr && arr.length)
    ? `<ul class="tight">${arr.map(x => `<li>${x}</li>`).join('')}</ul>` : '<p class="na">—</p>';
  $('summaryBody').innerHTML = `
    <div class="bars">${bars}</div>
    <h3>✨ 优秀表达</h3>${list(r.highlights)}
    <h3>⚠️ 高频错误</h3>${list(r.frequent_errors)}
    <h3>💡 推荐表达</h3>${list(r.recommended)}
    <h3>📌 训练建议</h3><div class="advice">${r.advice || '—'}</div>
    ${r.degraded ? '<p class="degraded">部分内容为降级生成</p>' : ''}`;
}

// ---------- 工具 ----------
function addBubble(who, text) {
  const b = document.createElement('div');
  b.className = 'bubble ' + (who === 'me' ? 'me' : 'ai');
  b.textContent = text;
  $('messages').appendChild(b); scrollDown();
  return b;
}
function scrollDown() { const m = $('messages'); m.scrollTop = m.scrollHeight; }
function fmt(v) { return v == null ? '—' : v; }
function playTTS(text) {
  const audio = new Audio('/api/tts?text=' + encodeURIComponent(text));
  audio.play().catch(() => {
    if (window.speechSynthesis) {
      const u = new SpeechSynthesisUtterance(text); u.lang = 'en-US';
      speechSynthesis.speak(u);
    }
  });
}
