"""课后总结单测:stub AIService 注入(design.md §22)。"""
import json

from report import ReportGenerator


class StubAI:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def chat(self, messages, *, system=None, max_tokens=1024) -> str:
        return self._reply


_GOOD = json.dumps({
    "highlights": ["I'm passionate about backend development"],
    "frequent_errors": ["subject-verb agreement"],
    "recommended": ["I'm keen on...", "I'd love to..."],
    "advice": "Practice present perfect vs simple past.",
})

_CORR = [
    {"original": "I has", "corrected": "I have", "category": "agreement"},
    {"original": "very like", "corrected": "really like", "category": "expression"},
]


def test_llm_summary_parsed():
    r = ReportGenerator(ai=StubAI(_GOOD)).summarize(
        scenario="interview",
        user_utterances=["I has worked here", "I very like coding"],
        corrections=_CORR)
    assert r.source == "llm" and not r.degraded
    assert r.highlights and r.recommended
    assert r.advice
    # 六维原始分本地计算,与 LLM 无关
    assert r.raw_skills.grammar is not None
    assert r.raw_skills.pronunciation is None


def test_fallback_when_unparseable():
    r = ReportGenerator(ai=StubAI("[mock reply] not json")).summarize(
        scenario="restaurant",
        user_utterances=["I want burger"],
        corrections=_CORR)
    assert r.source == "mock" and r.degraded
    # 本地兜底:用纠错拼出高频错误与推荐
    assert any("really like" in x for x in r.recommended)
    assert r.frequent_errors


def test_no_corrections_positive_advice():
    r = ReportGenerator(ai=StubAI("garbage")).summarize(
        scenario="interview",
        user_utterances=["I really enjoy solving hard problems."],
        corrections=[])
    assert r.degraded
    assert "保持" in r.advice or r.advice
