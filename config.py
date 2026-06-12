"""集中配置:从环境变量 / .env 读取,绝不硬编码任何密钥。

设计见 design.md §9.3、§25。判断各 provider 是否就绪由这里统一给出,
AIService 据此决定走真实接入还是 Mock(缺 key 也能把项目跑起来)。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# 轻量加载 .env(无 python-dotenv 时静默跳过,环境变量仍可生效)
try:  # pragma: no cover - 取决于运行环境
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))
except Exception:  # pragma: no cover
    pass


_PLACEHOLDER = {"", "replace-me", "your-key", "changeme"}


def _clean(value: str | None) -> str:
    """把占位值视作未配置,避免拿假 key 去打真实接口。"""
    v = (value or "").strip()
    return "" if v in _PLACEHOLDER else v


@dataclass(frozen=True)
class MiniMaxConfig:
    base_url: str = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic")
    api_key: str = _clean(os.getenv("MINIMAX_API_KEY"))
    llm_model: str = os.getenv("MINIMAX_LLM_MODEL", "MiniMax-M2")
    tts_model: str = os.getenv("MINIMAX_TTS_MODEL", "speech-2.6-turbo")
    tts_voice: str = os.getenv("MINIMAX_TTS_VOICE", "English_Trustworthy_Man")

    @property
    def ready(self) -> bool:
        return bool(self.api_key)

    @property
    def api_host(self) -> str:
        # base_url 形如 https://api.minimaxi.com/anthropic,取主机用于 TTS REST/WS
        from urllib.parse import urlparse

        return urlparse(self.base_url).netloc or "api.minimaxi.com"


@dataclass(frozen=True)
class AzureConfig:
    api_key: str = _clean(os.getenv("AZURE_SPEECH_KEY"))
    region: str = os.getenv("AZURE_SPEECH_REGION", "eastasia")

    @property
    def ready(self) -> bool:
        return bool(self.api_key and self.region)


@dataclass(frozen=True)
class HermesConfig:
    base: str = _clean(os.getenv("HERMES_BASE"))

    @property
    def ready(self) -> bool:
        return bool(self.base)


minimax = MiniMaxConfig()
azure = AzureConfig()
hermes = HermesConfig()


def status() -> dict[str, bool]:
    """各接入是否就绪,供连通性自检 / 启动日志使用。"""
    return {
        "minimax": minimax.ready,
        "azure": azure.ready,
        "hermes": hermes.ready,
    }
