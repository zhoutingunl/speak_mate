"""课后总结(design.md §5.5、§14)。

汇总单次会话:优秀表达 / 高频错误 / 推荐表达 / 训练建议,并算出本次六维原始分。
总结正文用 LLM(结构化 JSON,失败降级到基于纠错的本地汇总);六维分纯本地计算。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from ai import AIService, ChatMessage, get_service
from jsonutil import extract_json_object as _extract_json
from skills import SkillProfile, derive_raw_skills


@dataclass
class SessionSummary:
    highlights: list[str] = field(default_factory=list)      # 优秀表达
    frequent_errors: list[str] = field(default_factory=list)  # 高频错误
    recommended: list[str] = field(default_factory=list)      # 推荐表达
    advice: str = ""                                          # 训练建议
    raw_skills: SkillProfile = field(default_factory=SkillProfile)
    source: str = "llm"
    degraded: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["raw_skills"] = self.raw_skills.to_dict()
        return d


_PROMPT = (
    "You are an English speaking coach. Below is a learner's turns in a "
    "'{scenario}' role-play and the corrections made. Produce a short post-class "
    "summary as STRICT JSON only (no markdown):\n"
    '{{"highlights": ["good phrases the learner used"], '
    '"frequent_errors": ["recurring mistake patterns"], '
    '"recommended": ["2-4 better phrases to learn"], '
    '"advice": "one short paragraph of actionable advice"}}\n\n'
    "Learner turns:\n{turns}\n\nCorrections:\n{errors}"
)


class ReportGenerator:
    def __init__(self, ai: AIService | None = None) -> None:
        self.ai = ai or get_service()

    def summarize(self, *, scenario: str, user_utterances: list[str],
                  corrections: list[dict], completed: bool = True
                  ) -> SessionSummary:
        raw_skills = derive_raw_skills(
            user_utterances,
            correction_count=len(corrections),
            expression_issue_count=sum(
                1 for c in corrections if c.get("category") == "expression"),
            completed=completed,
        )

        turns_text = "\n".join(f"- {u}" for u in user_utterances) or "(none)"
        err_text = "\n".join(
            f"- {c.get('original','')} -> {c.get('corrected','')}"
            for c in corrections) or "(none)"
        prompt = _PROMPT.format(scenario=scenario, turns=turns_text,
                                errors=err_text)

        for budget in (3072, 5120):
            raw = self.ai.chat([ChatMessage("user", prompt)], max_tokens=budget)
            data = _extract_json(raw)
            if data is not None:
                return SessionSummary(
                    highlights=_strlist(data.get("highlights")),
                    frequent_errors=_strlist(data.get("frequent_errors")),
                    recommended=_strlist(data.get("recommended")),
                    advice=str(data.get("advice", "")),
                    raw_skills=raw_skills,
                    source="llm",
                )
        return self._local_fallback(corrections, raw_skills)

    @staticmethod
    def _local_fallback(corrections: list[dict],
                        raw_skills: SkillProfile) -> SessionSummary:
        """LLM 不可用时,用纠错数据拼一个诚实的本地总结。"""
        errors = [f"{c.get('original','')} → {c.get('corrected','')}"
                  for c in corrections if c.get("original")]
        recommended = [c.get("corrected", "") for c in corrections
                       if c.get("corrected")][:4]
        advice = ("本次共发现 {} 处可改进点;建议重点练习上面列出的纠错表达。"
                  .format(len(corrections)) if corrections
                  else "本次表达整体不错,继续保持并尝试更丰富的句式。")
        return SessionSummary(
            highlights=[], frequent_errors=errors[:5], recommended=recommended,
            advice=advice, raw_skills=raw_skills,
            source="mock", degraded=True,
        )


def _strlist(v) -> list[str]:
    return [str(x) for x in v] if isinstance(v, list) else []
