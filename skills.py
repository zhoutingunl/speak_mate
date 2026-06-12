"""六维能力模型与评分算法(design.md §14)。

EWMA 更新长期画像,抗单次抖动。可从纯文本信号推导的维度(Grammar/Vocabulary/
Expression/Communication)本期即可算;Pronunciation/Fluency 依赖 Azure,
拿不到时置 None(诚实,不臆造)。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

DIMENSIONS = ("pronunciation", "fluency", "grammar",
              "vocabulary", "expression", "communication")

ALPHA = 0.3  # EWMA 平滑系数,design.md §14.1


@dataclass
class SkillProfile:
    pronunciation: float | None = None
    fluency: float | None = None
    grammar: float | None = None
    vocabulary: float | None = None
    expression: float | None = None
    communication: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def update_profile(prev: SkillProfile, raw: SkillProfile,
                   alpha: float = ALPHA) -> SkillProfile:
    """EWMA 更新:score = α*raw + (1-α)*prev。

    - prev 维度为 None(冷启动)→ 直接采用 raw(α=1)。
    - raw 维度为 None(本次无数据,如缺 Azure)→ 保留 prev。
    """
    out = {}
    for dim in DIMENSIONS:
        p = getattr(prev, dim)
        r = getattr(raw, dim)
        if r is None:
            out[dim] = p
        elif p is None:
            out[dim] = round(r, 1)
        else:
            out[dim] = round(alpha * r + (1 - alpha) * p, 1)
    return SkillProfile(**out)


def derive_raw_skills(user_utterances: list[str], *, correction_count: int,
                      expression_issue_count: int,
                      completed: bool) -> SkillProfile:
    """从单次会话的文本信号推导本次六维原始分(design.md §14.1)。

    Pronunciation / Fluency 需声学数据,这里留 None,由发音评测旁路补充。
    """
    text = " ".join(user_utterances).strip()
    tokens = [t.lower() for t in text.split() if t.isalpha()]
    n_tokens = len(tokens)
    turns = len(user_utterances)

    if n_tokens == 0:
        return SkillProfile()

    # Grammar:按"每轮平均纠错数"扣分
    err_per_turn = correction_count / max(turns, 1)
    grammar = _clamp(100 - err_per_turn * 25)

    # Vocabulary:type-token ratio(去重词数 / 总词数),按词量加权避免短句虚高
    ttr = len(set(tokens)) / n_tokens
    coverage = min(n_tokens / 60.0, 1.0)  # 词太少不足以判断丰富度
    vocabulary = _clamp(40 + ttr * 60 * coverage + (1 - coverage) * 20)

    # Expression:表达类问题越少越自然
    expr_per_turn = expression_issue_count / max(turns, 1)
    expression = _clamp(100 - expr_per_turn * 30)

    # Communication:有效轮次 + 平均发言长度(过短/过长都不理想)
    avg_len = n_tokens / max(turns, 1)
    length_score = _clamp(100 - abs(avg_len - 14) * 4)  # 约 14 词/轮最佳
    communication = _clamp(0.6 * length_score + (40 if completed else 10)
                           + min(turns, 8) * 2.5)

    return SkillProfile(
        grammar=round(grammar, 1),
        vocabulary=round(vocabulary, 1),
        expression=round(expression, 1),
        communication=round(communication, 1),
    )


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))
