"""对话引擎单测:走 Mock,不打真实接口(design.md §22)。"""
import dataclasses

import config
import pytest
from ai.service import AIService
from conversation import ConversationEngine, SessionStore
from scenarios import SCENARIOS, get_scenario


@pytest.fixture
def engine(monkeypatch):
    # 强制 Mock,避免任何真实调用
    monkeypatch.setattr(config, "minimax",
                        dataclasses.replace(config.minimax, api_key=""))
    monkeypatch.setattr(config, "azure",
                        dataclasses.replace(config.azure, api_key=""))
    return ConversationEngine(ai=AIService(), store=SessionStore())


def test_scenarios_have_required_fields():
    for key, sc in SCENARIOS.items():
        assert sc.key == key
        assert sc.opening and sc.role and sc.goal
        assert "You are" in sc.system_prompt(3)


def test_system_prompt_varies_with_difficulty():
    sc = get_scenario("interview")
    assert sc.system_prompt(1) != sc.system_prompt(5)


def test_start_session_seeds_opening(engine):
    s = engine.start("interview")
    assert s.history[0].role == "assistant"
    assert s.history[0].content == get_scenario("interview").opening
    assert s.turns() == 0


def test_reply_appends_user_and_assistant(engine):
    s = engine.start("restaurant")
    out = engine.reply(s, "I'd like a burger please.")
    assert out
    assert s.turns() == 1
    assert s.history[-1].role == "assistant"
    assert s.history[-2].role == "user"


def test_reply_stream_yields_then_persists(engine):
    s = engine.start("interview")
    chunks = list(engine.reply_stream(s, "I studied computer science."))
    assert chunks
    assert s.history[-1].content == "".join(chunks).strip()


def test_context_window_trims(engine):
    s = engine.start("interview")
    for i in range(15):
        engine.reply(s, f"message number {i}")
    from conversation import MAX_HISTORY_MESSAGES
    assert len(s.history) <= MAX_HISTORY_MESSAGES


def test_empty_user_text_rejected(engine):
    s = engine.start("interview")
    with pytest.raises(ValueError):
        engine.reply(s, "   ")


def test_unknown_scenario_rejected(engine):
    with pytest.raises(ValueError):
        engine.start("nonexistent")


def test_invalid_difficulty_rejected(engine):
    with pytest.raises(ValueError):
        engine.start("interview", difficulty=9)
