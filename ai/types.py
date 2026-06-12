"""AI 接入层的数据结构。保持纯数据,便于跨模块/序列化与测试。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str

    def to_api(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class WordScore:
    """单词级发音结果(来自 Azure word-level)。"""

    word: str
    accuracy: float  # 0~100
    error_type: str = "None"  # None / Mispronunciation / Omission / Insertion

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PronScore:
    """发音评测结果。维度对应 design.md §12.1。

    source 标明来源:azure(真音素级)/ proxy(降级近似)/ mock(示例)。
    degraded=True 时前端必须显示"仅供参考"。
    """

    pronunciation: float  # AccuracyScore
    fluency: float
    prosody: float
    completeness: float
    overall: float
    transcript: str = ""
    words: list[WordScore] = field(default_factory=list)
    source: Literal["azure", "proxy", "mock"] = "azure"
    degraded: bool = False
    note: str = ""

    @staticmethod
    def weighted(accuracy: float, fluency: float, prosody: float,
                 completeness: float) -> float:
        """四维加权总分,权重见 design.md §12.1。"""
        return round(
            accuracy * 0.40 + fluency * 0.30 + prosody * 0.15 + completeness * 0.15,
            1,
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["words"] = [w if isinstance(w, dict) else w.to_dict() for w in self.words]
        return d
