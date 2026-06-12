"""设置:配置覆盖、持久化、设置接口(打码)单测。"""
import config
import db
from app import app as flask_app


def test_build_with_override():
    mm, az, _ = config.build({
        "MINIMAX_API_KEY": "abc123", "AZURE_SPEECH_KEY": "z",
        "AZURE_SPEECH_REGION": "westus"})
    assert mm.api_key == "abc123" and mm.ready
    assert az.region == "westus" and az.ready


def test_placeholder_treated_as_unset():
    mm, _, _ = config.build({"MINIMAX_API_KEY": "replace-me"})
    assert mm.api_key == "" and not mm.ready


def test_override_empty_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("MINIMAX_LLM_MODEL", "Custom-M")
    mm, _, _ = config.build({"MINIMAX_LLM_MODEL": ""})
    assert mm.llm_model == "Custom-M"


def test_db_settings_roundtrip(tmp_path):
    p = tmp_path / "s.sqlite"
    db.init_db(p)
    db.save_settings({"MINIMAX_API_KEY": "k1", "MINIMAX_LLM_MODEL": ""}, p)
    assert db.get_all_settings(p) == {"MINIMAX_API_KEY": "k1"}
    db.save_settings({"MINIMAX_API_KEY": ""}, p)  # 空 = 清除
    assert db.get_all_settings(p) == {}


def test_get_settings_masks_secret():
    client = flask_app.test_client()
    data = client.get("/api/settings").get_json()
    fields = {f["key"]: f for f in data["fields"]}
    mk = fields["MINIMAX_API_KEY"]
    assert mk["secret"] is True
    if mk["configured"]:
        assert "•" in mk["value"]          # 打码,不回显明文
        assert len(mk["value"]) < 20
    # 非密文字段直接给值
    assert fields["AZURE_SPEECH_REGION"]["secret"] is False
