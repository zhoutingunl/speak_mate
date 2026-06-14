"""自对弈核心单测:用 stub AI 驱动 run_selfplay,不打网络。"""
from selfplay import run_selfplay


class StubAI:
    """可控假 AIService:chat 返回带错句子;chat_stream 产出考官回复。"""
    llm_live = True
    pron_live = False

    def chat(self, messages, *, system=None, max_tokens=1024):
        # 学习者作答/场景生成/总结/评委 都走这里;返回非 JSON 触发各自兜底
        return "I very like this place."

    def chat_stream(self, messages, *, system=None, max_tokens=1024):
        yield "Thanks. "
        yield "Tell me more?"


def _events(turns=2):
    return list(run_selfplay(StubAI(), "interview", turns=turns,
                             difficulty=2, level="A2"))


def test_event_sequence():
    evs = _events(turns=2)
    types = [e["type"] for e in evs]
    assert types[0] == "start"
    assert types[1] == "tutor"            # 开场白
    assert types[-1] == "done"
    assert types.count("learner") == 2    # 两轮学习者作答
    assert "summary" in types and "judge" in types


def test_correction_event_fires_on_error():
    # "very like" 命中规则兜底 → 应产出 correction 事件
    evs = _events(turns=1)
    corr = [e for e in evs if e["type"] == "correction"]
    assert corr and any("really like" in i["corrected"] for i in corr[0]["items"])


def test_turns_clamped():
    evs = list(run_selfplay(StubAI(), "interview", turns=99))
    assert evs[0]["turns"] <= 8           # 上限保护


def test_summary_has_raw_skills():
    summary = next(e for e in _events(1) if e["type"] == "summary")
    assert "raw_skills" in summary
    assert summary["raw_skills"]["pronunciation"] is None  # 无人声
