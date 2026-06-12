"""AIService 单测:不打真实接口,验证 Mock/降级路径(design.md §22)。"""
import dataclasses

import config
from ai.service import AIService
from ai.types import ChatMessage, PronScore


def _force_mock(monkeypatch):
    """把所有 provider 置为未就绪,确保走 Mock(frozen dataclass 用 replace)。"""
    monkeypatch.setattr(config, "minimax",
                        dataclasses.replace(config.minimax, api_key=""))
    monkeypatch.setattr(config, "azure",
                        dataclasses.replace(config.azure, api_key=""))


def test_chat_falls_back_to_mock(monkeypatch):
    _force_mock(monkeypatch)
    svc = AIService()
    assert not svc.llm_live
    out = svc.chat([ChatMessage("user", "hello")])
    assert "mock reply" in out


def test_chat_stream_yields_chunks(monkeypatch):
    _force_mock(monkeypatch)
    svc = AIService()
    chunks = list(svc.chat_stream([ChatMessage("user", "hi there")]))
    assert chunks and "".join(chunks).strip()


def test_tts_stream_yields_bytes(monkeypatch):
    _force_mock(monkeypatch)
    svc = AIService()
    chunks = list(svc.synthesize_stream("hello world"))
    assert chunks and all(isinstance(c, bytes) for c in chunks)


def test_pron_degraded_when_no_azure(monkeypatch):
    _force_mock(monkeypatch)
    svc = AIService()
    assert not svc.pron_live
    score = svc.score_pronunciation("nonexistent.wav", "I have been to Paris.")
    assert isinstance(score, PronScore)
    assert score.degraded is True
    assert score.source in ("proxy", "mock")


def test_weighted_score():
    assert PronScore.weighted(100, 100, 100, 100) == 100.0
    assert 0 <= PronScore.weighted(50, 60, 70, 80) <= 100


class _Boom:
    """模拟 MiniMax 抛错(如 429 配额用尽)。"""
    def chat(self, *a, **k): raise RuntimeError("429 quota")
    def chat_stream(self, *a, **k): raise RuntimeError("429 quota"); yield
    def synthesize_stream(self, *a, **k): raise RuntimeError("429 quota"); yield


def test_chat_resilient_to_minimax_failure(monkeypatch):
    _force_mock(monkeypatch)
    svc = AIService()
    svc._minimax = _Boom()  # 故障注入
    # 不抛异常,降级到 Mock
    assert "mock reply" in svc.chat([ChatMessage("user", "hi")])
    assert list(svc.chat_stream([ChatMessage("user", "hi")]))
    # TTS 失败则静默(前端兜底),不抛
    assert list(svc.synthesize_stream("hello")) == []
