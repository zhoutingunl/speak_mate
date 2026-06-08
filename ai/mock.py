"""Mock 接入:无任何 key 时也能把项目跑起来(design.md §9.3)。

所有产出都明确标注为示例/降级,绝不冒充真实结果(诚实性,design.md §12.4)。
"""
from __future__ import annotations

import re
from collections.abc import Iterator

from .types import ChatMessage, PronScore, WordScore

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


class MockClient:
    """对话 + TTS 的假实现。TTS 返回静音占位字节。"""

    def chat(self, messages: list[ChatMessage], *, system: str | None = None,
             max_tokens: int = 1024) -> str:
        last = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return f"[mock reply] I heard you say: {last!r}. Could you tell me more?"

    def chat_stream(self, messages: list[ChatMessage], *, system: str | None = None,
                    max_tokens: int = 1024) -> Iterator[str]:
        for sentence in _SENT_SPLIT.split(self.chat(messages, system=system)):
            if sentence:
                yield sentence + " "

    def synthesize_stream(self, text: str, *, audio_format: str = "mp3",
                          sample_rate: int = 16000) -> Iterator[bytes]:
        # 每个词回一小段静音占位,保留"流式分片"的形状供前端联调
        for _ in text.split():
            yield b"\x00" * 320


def mock_pron_score(ref_text: str) -> PronScore:
    words = [WordScore(word=w, accuracy=80.0, error_type="None")
             for w in ref_text.split()]
    return PronScore(
        pronunciation=80.0, fluency=80.0, prosody=80.0, completeness=80.0,
        overall=PronScore.weighted(80, 80, 80, 80),
        transcript=ref_text, words=words,
        source="mock", degraded=True,
        note="Mock 示例分,未接入真实评测引擎",
    )
