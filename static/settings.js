'use strict';
const $ = (id) => document.getElementById(id);
const SRC_CN = { user: '已自定义', env: '来自环境变量', none: '未配置' };
let FIELDS = [];

load();
async function load() {
  const d = await fetch('/api/settings').then(r => r.json());
  FIELDS = d.fields;
  $('form').innerHTML = FIELDS.map(f => {
    const tag = `<span class="src ${f.source}">${SRC_CN[f.source]}</span>`;
    if (f.secret) {
      const ph = f.configured ? `当前:${f.value}(留空不改)` : '未配置,请粘贴 Key';
      return `<div class="set-row">
        <label>${f.label} ${tag}</label>
        <div class="set-input">
          <input type="password" data-key="${f.key}" placeholder="${ph}">
          ${f.configured ? `<button class="link" data-clear="${f.key}">清除</button>` : ''}
        </div></div>`;
    }
    return `<div class="set-row">
      <label>${f.label} ${tag}</label>
      <div class="set-input">
        <input type="text" data-key="${f.key}" value="${f.value || ''}" placeholder="默认值">
      </div></div>`;
  }).join('');

  $('form').querySelectorAll('[data-clear]').forEach(b =>
    b.onclick = () => clearKey(b.dataset.clear));
  $('saveBtn').onclick = save;
  $('testBtn').onclick = test;
  renderStatus(d.status);
}

function gather() {
  const set = {};
  $('form').querySelectorAll('input[data-key]').forEach(i => {
    if (i.value.trim()) set[i.dataset.key] = i.value.trim();
  });
  return set;
}

async function save() {
  msg('保存中…');
  const r = await fetch('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ set: gather() }),
  }).then(r => r.json());
  msg(r.ok ? '✅ 已保存并生效' : '保存失败');
  renderStatus(r.status);
  load();  // 刷新打码回显
}

async function clearKey(key) {
  if (!confirm('清除该项?将回落到环境变量(若有)。')) return;
  const r = await fetch('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clear: [key] }),
  }).then(r => r.json());
  renderStatus(r.status); load();
}

async function test() {
  msg('测试中(各打一发真实请求)…');
  // 先存当前输入,再测,确保测的是最新值
  await fetch('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ set: gather() }),
  });
  const r = await fetch('/api/settings/test', { method: 'POST' }).then(r => r.json());
  const row = (name, x) => {
    const icon = x.ok === true ? '✅' : (x.ok === null ? '⚠️' : '❌');
    return `<div class="test-row">${icon} <b>${name}</b> ${x.msg}</div>`;
  };
  $('result').innerHTML = `<div class="card">${row('MiniMax', r.minimax)}${row('Azure 发音评测', r.azure)}</div>`;
  load();
}

function renderStatus(s) {
  if (!s) return;
  $('result').dataset.status =
    `对话 ${s.llm_live ? '在线' : 'Mock'} · 发音 ${s.pron_live ? '在线' : '降级'}`;
}
function msg(t) { $('result').innerHTML = `<p class="hint">${t}</p>`; }
