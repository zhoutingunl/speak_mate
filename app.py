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

from ai import get_service
from conversation import ConversationEngine
from grammar import GrammarChecker
from report import ReportGenerator
from scenarios import SCENARIOS

app = Flask(__name__)

ai = get_service()
engine = ConversationEngine(ai=ai)
grammar = GrammarChecker(ai=ai)
reporter = ReportGenerator(ai=ai)

# session_id -> 已发现的纠错(供课后总结聚合)
_corrections: dict[str, list[dict]] = defaultdict(list)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def status():
    return jsonify({"llm_live": ai.llm_live, "pron_live": ai.pron_live})


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
    if "audio" not in request.files or not ref:
        return jsonify({"error": "缺少 audio 或 ref_text"}), 400

    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in"
        wav = Path(d) / "out.wav"
        request.files["audio"].save(src)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(src), "-ar", "16000", "-ac", "1",
                 "-sample_fmt", "s16", str(wav)],
                check=True, capture_output=True, timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            return jsonify({"error": f"音频转码失败: {e}"}), 400
        score = ai.score_pronunciation(str(wav), ref)
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
    summary = reporter.summarize(
        scenario=session.scenario_key,
        user_utterances=utterances,
        corrections=_corrections.get(sid, []),
        completed=session.turns() >= 3,
    )
    return jsonify(summary.to_dict())


if __name__ == "__main__":
    # 默认 5001:macOS 上 5000 被 ControlCenter(AirPlay)占用
    port = int(os.getenv("PORT", "5001"))
    print("== SpeakMate ==", {"llm_live": ai.llm_live, "pron_live": ai.pron_live},
          f"http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, threaded=True)
