"""AIService:接入层统一入口(design.md §9.1)。

业务代码只依赖本类。内部按配置就绪情况选择真实接入或 Mock,并实现降级:
- 对话/TTS:MiniMax 就绪则用真实接入,否则 Mock。
- 发音评测:Azure 就绪则真评测,否则透明降级(proxy/mock)。
"""
from __future__ import annotations

import logging
from collections.abc import Iterator

import config
from .mock import MockClient, mock_pron_score
from .types import ChatMessage, PronScore

log = logging.getLogger("speakmate.ai")


class AIService:
    def __init__(self) -> None:
        self._mock = MockClient()
        self._minimax = None
        self._azure = None

        if config.minimax.ready:
            try:
                from .minimax import MiniMaxClient

                self._minimax = MiniMaxClient(config.minimax)
            except Exception as e:  # pragma: no cover - 环境相关
                log.warning("MiniMax 初始化失败,退回 Mock:%s", e)

        if config.azure.ready:
            try:
                from .azure_pron import AzurePronProvider

                self._azure = AzurePronProvider(config.azure)
            except Exception as e:  # pragma: no cover - 环境相关
                log.warning("Azure 初始化失败,发音评测将降级:%s", e)

    # ---- 能力可用性,用于启动日志 / 自检 ----
    @property
    def llm_live(self) -> bool:
        return self._minimax is not None

    @property
    def pron_live(self) -> bool:
        return self._azure is not None

    # ---- 对话 ----
    def chat(self, messages: list[ChatMessage], *, system: str | None = None,
             max_tokens: int = 1024) -> str:
        client = self._minimax or self._mock
        return client.chat(messages, system=system, max_tokens=max_tokens)

    def chat_stream(self, messages: list[ChatMessage], *, system: str | None = None,
                    max_tokens: int = 1024) -> Iterator[str]:
        client = self._minimax or self._mock
        yield from client.chat_stream(messages, system=system, max_tokens=max_tokens)

    # ---- TTS ----
    def synthesize_stream(self, text: str, *, audio_format: str = "mp3",
                          sample_rate: int = 16000) -> Iterator[bytes]:
        client = self._minimax or self._mock
        yield from client.synthesize_stream(
            text, audio_format=audio_format, sample_rate=sample_rate)

    # ---- 发音评测 ----
    def score_pronunciation(self, audio_path: str, ref_text: str) -> PronScore:
        if self._azure is not None:
            try:
                return self._azure.score(audio_path, ref_text)
            except Exception as e:
                log.warning("Azure 发音评测失败,降级:%s", e)
        # 透明降级:本期先给 Mock 占位(代理分留待后续 PR),明确标注
        return mock_pron_score(ref_text)


_singleton: AIService | None = None


def get_service() -> AIService:
    global _singleton
    if _singleton is None:
        _singleton = AIService()
    return _singleton
