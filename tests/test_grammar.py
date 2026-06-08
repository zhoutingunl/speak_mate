"""纠错单测:用 stub AIService 注入,不打真实接口(design.md §22)。"""
import json

import pytest
from grammar import GrammarChecker, _extract_json


class StubAI:
    """可控的假 AIService,chat() 返回预设字符串。"""

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def chat(self, messages, *, system=None, max_tokens=1024) -> str:
        return self._reply


def _llm_json(has_issues=True):
    return json.dumps({
        "has_issues": has_issues,
        "polished": "I really like it.",
        "corrections": [
            {"original": "very like", "corrected": "really like",
             "reason": "程度副词", "category": "expression"}
        ] if has_issues else [],
    })


def test_parses_llm_json():
    gc = GrammarChecker(ai=StubAI(_llm_json()))
    r = gc.check("I very like it.")
    assert r.source == "llm" and not r.degraded
    assert r.has_issues
    assert r.corrections[0].corrected == "really like"
    assert r.polished == "I really like it."


def test_llm_clean_sentence():
    gc = GrammarChecker(ai=StubAI(_llm_json(has_issues=False)))
    r = gc.check("I like it.")
    assert not r.has_issues and r.corrections == []


def test_json_inside_markdown_fence():
    fenced = f"```json\n{_llm_json()}\n```"
    gc = GrammarChecker(ai=StubAI(fenced))
    assert gc.check("I very like it.").has_issues


def test_falls_back_to_rules_on_unparseable():
    # 模拟 Mock/异常输出,触发规则化兜底
    gc = GrammarChecker(ai=StubAI("[mock reply] not json at all"))
    r = gc.check("I very like it.")
    assert r.source == "mock" and r.degraded
    assert r.has_issues
    assert "really like" in r.polished


def test_rules_catch_have_went():
    gc = GrammarChecker(ai=StubAI("garbage"))
    r = gc.check("I have went to Paris.")
    assert r.has_issues and "have gone" in r.polished


def test_rules_no_false_positive():
    gc = GrammarChecker(ai=StubAI("garbage"))
    r = gc.check("I have gone to Paris.")
    assert not r.has_issues


def test_empty_text():
    gc = GrammarChecker(ai=StubAI(_llm_json()))
    r = gc.check("   ")
    assert not r.has_issues


@pytest.mark.parametrize("raw,ok", [
    ('{"a":1}', True),
    ('prefix {"a":1} suffix', True),
    ("no json here", False),
    ("", False),
    ("[1,2,3]", False),  # 数组不算我们要的对象
])
def test_extract_json(raw, ok):
    assert (_extract_json(raw) is not None) == ok
