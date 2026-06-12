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
        self._asr = None
        self._setup_providers()

    def _setup_providers(self) -> None:
        """按当前 config 构建/重建真实接入(供初始化与热重载共用)。"""
        self._minimax = None
        self._azure = None
        self._asr = None
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

        if config.bailian.ready:
            try:
                from .bailian_asr import BailianASRProvider

                self._asr = BailianASRProvider(config.bailian)
            except Exception as e:  # pragma: no cover - 环境相关
                log.warning("百炼 ASR 初始化失败:%s", e)

    def reload(self) -> None:
        """配置变更后热重载接入(无需重启进程)。"""
        self._setup_providers()

    # ---- 能力可用性,用于启动日志 / 自检 ----
    @property
    def llm_live(self) -> bool:
        return self._minimax is not None

    @property
    def pron_live(self) -> bool:
        return self._azure is not None

    @property
    def asr_live(self) -> bool:
        return self._asr is not None

    # ---- ASR(浏览器兜底)----
    def transcribe(self, wav_path: str, *, language: str = "en") -> str:
        """服务端 ASR(百炼)。无 provider 时返回空串,由调用方处理。"""
        if self._asr is None:
            return ""
        return self._asr.transcribe(wav_path, language=language)

    # ---- 对话 ----
    def chat(self, messages: list[ChatMessage], *, system: str | None = None,
             max_tokens: int = 1024) -> str:
        if self._minimax is not None:
            try:
                return self._minimax.chat(messages, system=system,
                                          max_tokens=max_tokens)
            except Exception as e:  # 429/超时/网络 → 降级,绝不向上抛(design.md §16)
                log.warning("MiniMax chat 失败,降级 Mock:%s", e)
        return self._mock.chat(messages, system=system, max_tokens=max_tokens)

    def chat_stream(self, messages: list[ChatMessage], *, system: str | None = None,
                    max_tokens: int = 1024) -> Iterator[str]:
        if self._minimax is not None:
            produced = False
            try:
                for chunk in self._minimax.chat_stream(
                        messages, system=system, max_tokens=max_tokens):
                    produced = True
                    yield chunk
                return
            except Exception as e:
                log.warning("MiniMax chat_stream 失败,降级:%s", e)
                if produced:
                    return  # 已吐过内容,不再混入 Mock
        yield from self._mock.chat_stream(messages, system=system,
                                          max_tokens=max_tokens)

    # ---- TTS ----
    def synthesize_stream(self, text: str, *, audio_format: str = "mp3",
                          sample_rate: int = 16000) -> Iterator[bytes]:
        if self._minimax is not None:
            try:
                yield from self._minimax.synthesize_stream(
                    text, audio_format=audio_format, sample_rate=sample_rate)
                return
            except Exception as e:
                log.warning("MiniMax TTS 失败,前端将回退浏览器合成:%s", e)
                return  # 前端 SpeechSynthesis 兜底
        yield from self._mock.synthesize_stream(
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
