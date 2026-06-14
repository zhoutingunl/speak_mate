"""Flask 路由测试:只覆盖不触发 AI 的路径(会话/校验/错误码)。

对话/纠错/总结等需 AI 的接口在各自模块单测里用 Mock 覆盖,这里不重复打网络。
"""
import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


def test_index_serves(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"SpeakMate" in r.data


def test_scenarios(client):
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    keys = {s["key"] for s in r.get_json()}
    assert {"interview", "restaurant"} <= keys


def test_start_session_ok(client):
    r = client.post("/api/session", json={"scenario": "interview", "difficulty": 2})
    assert r.status_code == 200
    body = r.get_json()
    assert body["session_id"] and body["opening"]


def test_start_session_bad_scenario(client):
    r = client.post("/api/session", json={"scenario": "nope"})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_scenarios_have_custom_flag(client):
    assert all("custom" in s for s in client.get("/api/scenarios").get_json())


def test_add_scenario_requires_name(client):
    r = client.post("/api/scenarios", json={"description": "x"})
    assert r.status_code == 400


def test_delete_builtin_scenario_rejected(client):
    r = client.delete("/api/scenarios/interview")
    assert r.status_code == 400


def test_chat_unknown_session_404(client):
    r = client.post("/api/chat", json={"session_id": "nope", "text": "hi"})
    assert r.status_code == 404


def test_correct_empty_text_400(client):
    r = client.post("/api/correct", json={"session_id": "x", "text": "  "})
    assert r.status_code == 400


def test_pronounce_missing_fields_400(client):
    r = client.post("/api/pronounce", data={})
    assert r.status_code == 400


def test_tts_missing_text_400(client):
    r = client.get("/api/tts")
    assert r.status_code == 400


def test_status_reports_asr(client):
    r = client.get("/api/status")
    assert "asr_live" in r.get_json()


def test_transcribe_missing_audio_400(client):
    r = client.post("/api/transcribe", data={})
    assert r.status_code == 400


def test_voices(client):
    d = client.get("/api/voices").get_json()
    assert d["voices"] and "auto" in d["languages"]
    assert all("id" in v and "name" in v for v in d["voices"])


def test_settings_voice_has_choices(client):
    fields = {f["key"]: f for f in client.get("/api/settings").get_json()["fields"]}
    assert fields["MINIMAX_TTS_VOICE"].get("choices")
    assert fields["MINIMAX_TTS_LANGUAGE"].get("choices")
