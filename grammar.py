"""语法 / 表达纠错(design.md §13)。

对用户单轮发言做延迟纠错,产出结构化「错误句 → 原因 → 推荐表达」。
真实接入:LLM 返回严格 JSON;解析失败或无 key 时退化为规则化 Mock(明确标注)。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field
from typing import Literal

from ai import AIService, ChatMessage, get_service
from jsonutil import extract_json_object as _extract_json

Category = Literal["grammar", "expression", "tense", "article",
                   "preposition", "agreement"]


@dataclass
class Correction:
    original: str
    corrected: str
    reason: str
    category: str = "grammar"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CorrectionResult:
    has_issues: bool
    polished: str                       # 整句润色后的自然表达
    corrections: list[Correction] = field(default_factory=list)
    source: Literal["llm", "mock"] = "llm"
    degraded: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["corrections"] = [c if isinstance(c, dict) else c.to_dict()
                            for c in self.corrections]
        return d


_PROMPT = (
    "You are an English writing coach for a {level} learner. "
    "Analyze ONLY the user's sentence for grammar and expression issues "
    "(tense, prepositions, articles, subject-verb agreement, word choice, "
    "naturalness). Reply with STRICT JSON only, no markdown, shape:\n"
    '{{"has_issues": true/false, '
    '"polished": "natural corrected version of the whole sentence", '
    '"corrections": [{{"original": "...", "corrected": "...", '
    '"reason": "short reason", "category": '
    '"grammar|expression|tense|article|preposition|agreement"}}]}}\n'
    "If already correct and natural, has_issues=false, corrections=[], "
    "polished=original.\n\nUser sentence: {text!r}"
)

# 规则化兜底(无 key / 解析失败时用,只覆盖最典型的几例,诚实标注)
_RULES: list[tuple[re.Pattern, str, str, str]] = [
    (re.compile(r"\bvery\s+like\b", re.I), "very like", "really like",
     "'like' 是动词,程度副词用 really/very much 而非 very"),
    (re.compile(r"\bhave\s+went\b", re.I), "have went", "have gone",
     "现在完成时用过去分词 gone,不是 went"),
    (re.compile(r"\bi\s+am\s+agree\b", re.I), "am agree", "agree",
     "agree 本身是动词,不加 be"),
]


class GrammarChecker:
    def __init__(self, ai: AIService | None = None) -> None:
        self.ai = ai or get_service()

    # MiniMax-M2 含 thinking,偶尔吃光 token 预算导致正文为空;失败时加大预算重试一次
    _BUDGETS = (3072, 5120)

    def check(self, text: str, level: str = "B1") -> CorrectionResult:
        text = (text or "").strip()
        if not text:
            return CorrectionResult(False, "", source="mock", degraded=True)

        prompt = _PROMPT.format(level=level, text=text)
        for budget in self._BUDGETS:
            raw = self.ai.chat([ChatMessage("user", prompt)], max_tokens=budget)
            parsed = _extract_json(raw)
            if parsed is not None:
                return self._from_json(parsed)
        # 多次仍解析失败(含 Mock 回复)→ 规则化兜底,诚实标注降级
        return self._rule_based(text)

    @staticmethod
    def _from_json(data: dict) -> CorrectionResult:
        corrections = [
            Correction(
                original=str(c.get("original", "")),
                corrected=str(c.get("corrected", "")),
                reason=str(c.get("reason", "")),
                category=str(c.get("category", "grammar")),
            )
            for c in data.get("corrections", [])
            if isinstance(c, dict)
        ]
        return CorrectionResult(
            has_issues=bool(data.get("has_issues", bool(corrections))),
            polished=str(data.get("polished", "")),
            corrections=corrections,
            source="llm",
            degraded=False,
        )

    @staticmethod
    def _rule_based(text: str) -> CorrectionResult:
        polished = text
        found: list[Correction] = []
        for pat, original, corrected, reason in _RULES:
            if pat.search(polished):
                polished = pat.sub(corrected, polished)
                found.append(Correction(original, corrected, reason, "grammar"))
        return CorrectionResult(
            has_issues=bool(found),
            polished=polished,
            corrections=found,
            source="mock",
            degraded=True,
        )
