"""SpeakMate Flask 应用(design.md §7、§8)。

SPA 单页 + REST/流式接口:
- 浏览器 Web Speech API 做 ASR(关键路径),文本经 /api/chat 流式拿回复;
- /api/tts 流式返回 MiniMax 合成音频(边收边播);
- 录音旁路 /api/pronounce → ffmpeg 转 wav → Azure 发音评测;
- /api/correct 延迟纠错,/api/report 课后总结。
会话存内存(ConversationEngine 的 SessionStore)。
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

import config
import db
from ai import ChatMessage, get_service
from conversation import ConversationEngine
from dashboard import get_dashboard
from grammar import GrammarChecker
from report import ReportGenerator
from scenarios import SCENARIOS
from skills import DIMENSIONS, SkillProfile, update_profile

app = Flask(__name__)

# 先初始化库、套用用户保存的设置(Key 等),再构建接入层
db.init_db()
config.apply_overrides(db.get_all_settings())

ai = get_service()
engine = ConversationEngine(ai=ai)
grammar = GrammarChecker(ai=ai)
reporter = ReportGenerator(ai=ai)

# 设置页字段定义(secret 项回显打码)
SETTINGS_FIELDS = [
    {"key": "MINIMAX_API_KEY", "label": "MiniMax API Key", "secret": True},
    {"key": "MINIMAX_LLM_MODEL", "label": "MiniMax 对话模型", "secret": False},
    {"key": "MINIMAX_TTS_MODEL", "label": "MiniMax TTS 模型", "secret": False},
    {"key": "MINIMAX_TTS_VOICE", "label": "TTS 音色", "secret": False},
    {"key": "AZURE_SPEECH_KEY", "label": "Azure 语音 Key", "secret": True},
    {"key": "AZURE_SPEECH_REGION", "label": "Azure 区域", "secret": False},
    {"key": "DASHSCOPE_API_KEY", "label": "百炼 ASR Key(浏览器兜底)", "secret": True},
]


def _mask(secret: str) -> str:
    if not secret:
        return ""
    return (secret[:3] + "•••" + secret[-4:]) if len(secret) > 8 else "••••"

# session_id -> 已发现的纠错(供课后总结聚合)
_corrections: dict[str, list[dict]] = defaultdict(list)
# session_id -> 每轮 Azure 发音分 (pronunciation, fluency),供六维聚合
_pron_scores: dict[str, list[tuple[float, float]]] = defaultdict(list)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def status():
    return jsonify({"llm_live": ai.llm_live, "pron_live": ai.pron_live,
                    "asr_live": ai.asr_live})


def _blob_to_wav(file_storage, dst_dir: str) -> str:
    """把上传的任意格式录音转成 16k 单声道 WAV,返回路径。"""
    src = Path(dst_dir) / "in"
    wav = Path(dst_dir) / "out.wav"
    file_storage.save(src)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ar", "16000", "-ac", "1",
         "-sample_fmt", "s16", str(wav)],
        check=True, capture_output=True, timeout=30)
    return str(wav)


@app.post("/api/transcribe")
def transcribe():
    """浏览器兜底 ASR(百炼):上传录音 → wav → 文本。"""
    if "audio" not in request.files:
        return jsonify({"error": "缺少 audio"}), 400
    if not ai.asr_live:
        return jsonify({"error": "服务端 ASR 未配置", "text": ""}), 503
    with tempfile.TemporaryDirectory() as d:
        try:
            wav = _blob_to_wav(request.files["audio"], d)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            return jsonify({"error": f"音频转码失败: {e}"}), 400
        try:
            text = ai.transcribe(wav)
        except Exception as e:
            return jsonify({"error": str(e)[:140], "text": ""}), 502
    return jsonify({"text": text})


@app.get("/api/scenarios")
def scenarios():
    return jsonify([
        {"key": s.key, "name": s.name, "goal": s.goal, "opening": s.opening}
        for s in SCENARIOS.values()
    ])


@app.post("/api/session")
def new_session():
    data = request.get_json(force=True)
    try:
        session = engine.start(
            data.get("scenario", "interview"),
            int(data.get("difficulty", 2)),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    _corrections.pop(session.id, None)
    _pron_scores.pop(session.id, None)
    db.create_session(session.id, session.scenario_key, session.difficulty)
    return jsonify({"session_id": session.id,
                    "opening": session.history[0].content})


@app.post("/api/chat")
def chat():
    """SSE 流式回复(首句优先)。"""
    data = request.get_json(force=True)
    sid, text = data.get("session_id"), (data.get("text") or "").strip()
    try:
        session = engine.store.get(sid)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    if not text:
        return jsonify({"error": "空发言"}), 400

    def gen():
        try:
            for chunk in engine.reply_stream(session, text):
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
        except Exception as e:  # 兜底:不让前端 hang
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(gen(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.get("/api/tts")
def tts():
    text = (request.args.get("text") or "").strip()
    if not text:
        return jsonify({"error": "缺少 text"}), 400

    def gen():
        try:
            yield from ai.synthesize_stream(text, audio_format="mp3")
        except Exception:
            return  # 合成失败前端会回退浏览器 SpeechSynthesis

    return Response(gen(), mimetype="audio/mpeg",
                    headers={"Cache-Control": "no-cache"})


@app.post("/api/correct")
def correct():
    """对用户单轮发言做延迟纠错,并累积进会话供课后总结。"""
    data = request.get_json(force=True)
    sid, text = data.get("session_id"), (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "空发言"}), 400
    result = grammar.check(text)
    if sid and result.has_issues:
        _corrections[sid].extend(c.to_dict() for c in result.corrections)
    return jsonify(result.to_dict())


@app.post("/api/pronounce")
def pronounce():
    """上传录音(任意格式)→ ffmpeg 转 16k 单声道 wav → Azure 评测。"""
    ref = (request.form.get("ref_text") or "").strip()
    sid = request.form.get("session_id")
    if "audio" not in request.files or not ref:
        return jsonify({"error": "缺少 audio 或 ref_text"}), 400

    with tempfile.TemporaryDirectory() as d:
        try:
            wav = _blob_to_wav(request.files["audio"], d)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            return jsonify({"error": f"音频转码失败: {e}"}), 400
        score = ai.score_pronunciation(wav, ref)
    if sid and score.source == "azure" and not score.degraded:
        _pron_scores[sid].append((score.pronunciation, score.fluency))
    return jsonify(score.to_dict())


@app.post("/api/report")
def report():
    data = request.get_json(force=True)
    sid = data.get("session_id")
    try:
        session = engine.store.get(sid)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    utterances = [m.content for m in session.history if m.role == "user"]
    corrections = _corrections.get(sid, [])
    summary = reporter.summarize(
        scenario=session.scenario_key,
        user_utterances=utterances,
        corrections=corrections,
        completed=session.turns() >= 3,
    )

    # 把本次 Azure 发音分(逐轮均值)注入六维的声学维度(design.md §14)
    pron = _pron_scores.get(sid, [])
    if pron:
        summary.raw_skills.pronunciation = round(sum(p for p, _ in pron) / len(pron), 1)
        summary.raw_skills.fluency = round(sum(f for _, f in pron) / len(pron), 1)

    # EWMA 更新长期画像并落盘(design.md §14)
    prev = SkillProfile(**(db.get_user_skill() or {}))
    updated = update_profile(prev, summary.raw_skills)
    vals = [getattr(updated, d) for d in DIMENSIONS if getattr(updated, d) is not None]
    overall = round(sum(vals) / len(vals), 1) if vals else None
    db.finish_session(
        sid, turns=session.turns(),
        raw_skills=summary.raw_skills.to_dict(), profile=updated.to_dict(),
        overall=overall,
        correction_categories=[c.get("category", "grammar") for c in corrections],
    )

    out = summary.to_dict()
    out["profile"] = updated.to_dict()  # 累计六维(供前端展示成长)
    return jsonify(out)


@app.get("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")


@app.get("/api/dashboard")
def dashboard_data():
    return jsonify(get_dashboard())


# ---------- 设置(让用户配置自己的 Key)----------
@app.get("/settings")
def settings_page():
    return render_template("settings.html")


@app.get("/api/settings")
def get_settings():
    import os
    user = db.get_all_settings()
    fields = []
    for f in SETTINGS_FIELDS:
        k = f["key"]
        eff = user.get(k) or os.getenv(k, "")
        source = "user" if user.get(k) else ("env" if os.getenv(k) else "none")
        item = {**f, "source": source, "configured": bool(eff)}
        item["value"] = _mask(eff) if f["secret"] else eff
        fields.append(item)
    return jsonify({"fields": fields,
                    "status": {"llm_live": ai.llm_live, "pron_live": ai.pron_live}})


@app.post("/api/settings")
def save_settings():
    data = request.get_json(force=True)
    to_set = {k: v.strip() for k, v in (data.get("set") or {}).items()
              if k in config.SETTING_KEYS and isinstance(v, str) and v.strip()}
    to_clear = {k: "" for k in (data.get("clear") or []) if k in config.SETTING_KEYS}
    db.save_settings({**to_set, **to_clear})
    config.apply_overrides(db.get_all_settings())  # 热加载
    ai.reload()
    return jsonify({"ok": True,
                    "status": {"llm_live": ai.llm_live, "pron_live": ai.pron_live}})


@app.post("/api/settings/test")
def test_settings():
    """用当前生效配置各打一发真实请求,验证 Key 是否可用。"""
    return jsonify({"minimax": _test_minimax(), "azure": _test_azure(),
                    "bailian": _test_bailian()})


def _test_minimax() -> dict:
    if not config.minimax.ready:
        return {"ok": False, "msg": "未配置 Key"}
    try:
        from ai.minimax import MiniMaxClient
        out = MiniMaxClient(config.minimax).chat(
            [ChatMessage("user", "Reply with: OK")], max_tokens=1500)
        return {"ok": bool(out), "msg": (out[:40] or "空回复")}
    except Exception as e:
        return {"ok": False, "msg": str(e)[:140]}


def _test_azure() -> dict:
    if not config.azure.ready:
        return {"ok": False, "msg": "未配置 Key"}
    sample = Path(__file__).with_name("data") / "eval/sample.wav"
    if not sample.exists():
        return {"ok": None, "msg": "缺样本音频,跳过"}
    try:
        from ai.azure_pron import AzurePronProvider
        s = AzurePronProvider(config.azure).score(str(sample), "I have been to Paris.")
        return {"ok": True, "msg": f"overall={s.overall} «{s.transcript}»"}
    except Exception as e:
        return {"ok": False, "msg": str(e)[:140]}


def _test_bailian() -> dict:
    if not config.bailian.ready:
        return {"ok": False, "msg": "未配置 Key"}
    sample = Path(__file__).with_name("data") / "eval/sample.wav"
    if not sample.exists():
        return {"ok": None, "msg": "缺样本音频,跳过"}
    try:
        from ai.bailian_asr import BailianASRProvider
        text = BailianASRProvider(config.bailian).transcribe(str(sample))
        return {"ok": bool(text), "msg": f"«{text}»" if text else "空转写"}
    except Exception as e:
        return {"ok": False, "msg": str(e)[:140]}


if __name__ == "__main__":
    # 默认 5001:macOS 上 5000 被 ControlCenter(AirPlay)占用
    port = int(os.getenv("PORT", "5001"))
    print("== SpeakMate ==", {"llm_live": ai.llm_live, "pron_live": ai.pron_live},
          f"http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, threaded=True)
