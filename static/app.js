'use strict';

const $ = (id) => document.getElementById(id);
const state = { scenario: null, sessionId: null, recog: null, recorder: null,
                chunks: [], transcript: '', blob: null, recogDone: false,
                recDone: false, pronLive: false, asrLive: false,
                webSpeech: false, useServer: false };

const DIFF_LABELS = { 1: 'L1 · 入门', 2: 'L2 · 日常', 3: 'L3 · 自然',
                      4: 'L4 · 进阶', 5: 'L5 · 母语级' };

// ---------- 启动 ----------
init();
async function init() {
  const st = await fetch('/api/status').then(r => r.json()).catch(() => ({}));
  state.pronLive = !!st.pron_live;
  state.asrLive = !!st.asr_live;
  $('status').innerHTML =
    `对话 <b class="${st.llm_live ? 'ok' : 'off'}">${st.llm_live ? '在线' : 'Mock'}</b> · ` +
    `发音评测 <b class="${st.pron_live ? 'ok' : 'off'}">${st.pron_live ? '在线' : '降级'}</b>`;

  await loadScenarios();
  setupCustomScenario();

  $('difficulty').oninput = (e) => $('difficultyLabel').textContent = DIFF_LABELS[e.target.value];
  $('startBtn').onclick = startSession;
  $('endBtn').onclick = endSession;
  $('restartBtn').onclick = () => location.reload();
  setupMic();
}

async function loadScenarios(selectKey) {
  const scenarios = await fetch('/api/scenarios').then(r => r.json());
  const grid = $('scenarioList');
  grid.innerHTML = '';
  scenarios.forEach(sc => {
    const el = document.createElement('div');
    el.className = 'scenario';
    const del = sc.custom
      ? `<button class="cs-del" title="删除" data-key="${sc.key}">✕</button>` : '';
    el.innerHTML = `${del}<div class="name">${sc.name}</div>` +
      `<div class="goal">${sc.goal}</div>`;
    el.onclick = (e) => {
      if (e.target.classList.contains('cs-del')) return;
      document.querySelectorAll('.scenario').forEach(n => n.classList.remove('sel'));
      el.classList.add('sel');
      state.scenario = sc;
      $('startBtn').disabled = false;
    };
    grid.appendChild(el);
    if (sc.key === selectKey) el.click();
  });
  grid.querySelectorAll('.cs-del').forEach(b =>
    b.onclick = () => deleteScenario(b.dataset.key));
}

function setupCustomScenario() {
  $('addScenarioBtn').onclick = () =>
    $('addScenarioForm').classList.toggle('hidden');
  $('csSubmit').onclick = async () => {
    const name = $('csName').value.trim();
    const description = $('csDesc').value.trim();
    if (!name) { $('csHint').textContent = '请填场景名称'; return; }
    $('csSubmit').disabled = true;
    $('csHint').textContent = 'AI 正在生成场景…';
    try {
      const sc = await fetch('/api/scenarios', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description }),
      }).then(r => r.json());
      if (sc.error) { $('csHint').textContent = sc.error; return; }
      $('csName').value = ''; $('csDesc').value = '';
      $('addScenarioForm').classList.add('hidden');
      $('csHint').textContent = '';
      await loadScenarios(sc.key);  // 刷新并自动选中新场景
    } finally {
      $('csSubmit').disabled = false;
    }
  };
}

async function deleteScenario(key) {
  if (!confirm('删除这个自定义场景?')) return;
  await fetch('/api/scenarios/' + encodeURIComponent(key), { method: 'DELETE' });
  state.scenario = null; $('startBtn').disabled = true;
  await loadScenarios();
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

// ---------- 麦克风 ----------
// ASR 两条路:浏览器 Web Speech(主,Chrome/Edge)/ 服务端百炼(兜底,Safari/Firefox 默认)
function setupMic() {
  state.webSpeech = !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  // Chrome/Edge 且服务端 ASR 可用 → 给个「用百炼识别」开关;否则按可用性决定
  if (state.webSpeech && state.asrLive) {
    $('asrToggleWrap').classList.remove('hidden');
  }
  if (!state.webSpeech) {
    if (state.asrLive) {
      $('micHint').textContent = '本浏览器用百炼识别(服务端)';
    } else {
      $('micHint').textContent = '此浏览器不支持识别,且未配置百炼 ASR(去设置页配置)';
      $('micBtn').disabled = true;
    }
  }

  const btn = $('micBtn');
  const start = (e) => { e.preventDefault(); beginTurn(); };
  const stop = (e) => { e.preventDefault(); finishTurn(); };
  btn.addEventListener('pointerdown', start);
  btn.addEventListener('pointerup', stop);
  btn.addEventListener('pointerleave', stop);
}

function serverMode() {
  const forced = $('asrToggle') && $('asrToggle').checked;
  return state.asrLive && (forced || !state.webSpeech);
}

async function beginTurn() {
  const btn = $('micBtn');
  btn.classList.add('rec'); btn.textContent = '松开结束';
  state.transcript = ''; state.blob = null; state.chunks = [];
  state.recogDone = false; state.recDone = false;
  state.useServer = serverMode();
  track('voice_start', { server: state.useServer });

  // 浏览器 ASR(仅非服务端模式)
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!state.useServer && SR) {
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

  // 录音:给发音评测用,服务端模式下也用来送百炼 ASR
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const rec = new MediaRecorder(stream);
    rec.ondataavailable = (e) => state.chunks.push(e.data);
    rec.onstop = async () => {
      state.blob = new Blob(state.chunks, { type: rec.mimeType });
      stream.getTracks().forEach(t => t.stop());
      if (state.useServer) {
        $('micHint').textContent = '识别中…';
        const text = await serverTranscribe(state.blob);
        $('micHint').textContent = state.webSpeech ? '' : '本浏览器用百炼识别(服务端)';
        if (text) processTurn(text, state.blob);
        else $('micHint').textContent = '没听清,请再说一遍';
      } else {
        state.recDone = true; maybeProcess();
      }
    };
    state.recorder = rec; rec.start();
  } catch (err) { state.recDone = true; }
}

function finishTurn() {
  const btn = $('micBtn');
  btn.classList.remove('rec'); btn.textContent = '按住说话';
  track('voice_finish', {});
  try { state.recog && state.recog.stop(); } catch (e) { state.recogDone = true; }
  try { state.recorder && state.recorder.state !== 'inactive' && state.recorder.stop(); }
  catch (e) { state.recDone = true; }
}

async function serverTranscribe(blob) {
  const fd = new FormData();
  fd.append('audio', blob, 'rec.webm');
  try {
    const r = await fetch('/api/transcribe', { method: 'POST', body: fd })
      .then(r => r.json());
    return (r.text || '').trim();
  } catch (e) { return ''; }
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
  fd.append('session_id', state.sessionId);
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
    (r.polished ? `<div class="fix">建议:<span class="new">${r.polished}</span></div>` : '') +
    `<button class="link accept-btn">✓ 采纳</button>`;
  container.appendChild(c);
  const btn = c.querySelector('.accept-btn');
  btn.onclick = () => {
    track('suggestion_accept', { count: r.corrections.length });
    btn.textContent = '✓ 已采纳'; btn.disabled = true;
  };
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

// 用户行为采集(打点),fire-and-forget(design.md §19)
function track(event, payload) {
  try {
    fetch('/api/track', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event, payload: payload || {} }), keepalive: true,
    });
  } catch (e) { /* 埋点失败不影响主流程 */ }
}
function playTTS(text) {
  const audio = new Audio('/api/tts?text=' + encodeURIComponent(text));
  audio.play().catch(() => {
    if (window.speechSynthesis) {
      const u = new SpeechSynthesisUtterance(text); u.lang = 'en-US';
      speechSynthesis.speak(u);
    }
  });
}
