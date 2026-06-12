"""集中配置:环境变量 / .env 为底,运行时可被用户在设置页保存的值覆盖。

设计见 design.md §9.3、§25。绝不硬编码密钥;DB 覆盖值由 apply_overrides 注入,
便于「配置自己的 Key」热生效。判断各 provider 是否就绪也在这里统一给出。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

# 轻量加载 .env(无 python-dotenv 时静默跳过,环境变量仍可生效)
try:  # pragma: no cover - 取决于运行环境
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))
except Exception:  # pragma: no cover
    pass


_PLACEHOLDER = {"", "replace-me", "your-key", "changeme"}

# 可被设置页覆盖的配置项(环境变量名)
SETTING_KEYS = (
    "MINIMAX_API_KEY", "MINIMAX_LLM_MODEL", "MINIMAX_TTS_MODEL", "MINIMAX_TTS_VOICE",
    "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION",
)


def _clean(value: str | None) -> str:
    """把占位值视作未配置,避免拿假 key 去打真实接口。"""
    v = (value or "").strip()
    return "" if v in _PLACEHOLDER else v


@dataclass(frozen=True)
class MiniMaxConfig:
    base_url: str = "https://api.minimaxi.com/anthropic"
    api_key: str = ""
    llm_model: str = "MiniMax-M2"
    tts_model: str = "speech-2.6-turbo"
    tts_voice: str = "English_Trustworthy_Man"

    @property
    def ready(self) -> bool:
        return bool(self.api_key)

    @property
    def api_host(self) -> str:
        return urlparse(self.base_url).netloc or "api.minimaxi.com"


@dataclass(frozen=True)
class AzureConfig:
    api_key: str = ""
    region: str = "eastasia"

    @property
    def ready(self) -> bool:
        return bool(self.api_key and self.region)


@dataclass(frozen=True)
class HermesConfig:
    base: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.base)


def _source(overrides: dict[str, str] | None):
    """取值优先级:用户覆盖(非空) > 环境变量 > 默认。"""
    ov = overrides or {}

    def get(key: str, default: str = "") -> str:
        v = ov.get(key)
        if not v:
            v = os.getenv(key, default)
        return v or default

    return get


def build(overrides: dict[str, str] | None = None
          ) -> tuple[MiniMaxConfig, AzureConfig, HermesConfig]:
    get = _source(overrides)
    mm = MiniMaxConfig(
        base_url=get("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic"),
        api_key=_clean(get("MINIMAX_API_KEY")),
        llm_model=get("MINIMAX_LLM_MODEL", "MiniMax-M2"),
        tts_model=get("MINIMAX_TTS_MODEL", "speech-2.6-turbo"),
        tts_voice=get("MINIMAX_TTS_VOICE", "English_Trustworthy_Man"),
    )
    az = AzureConfig(api_key=_clean(get("AZURE_SPEECH_KEY")),
                     region=get("AZURE_SPEECH_REGION", "eastasia"))
    he = HermesConfig(base=_clean(get("HERMES_BASE")))
    return mm, az, he


# 模块级当前生效配置(env 为底);设置页保存后由 apply_overrides 刷新
minimax, azure, hermes = build()


def apply_overrides(overrides: dict[str, str]) -> None:
    """用用户保存的值覆盖并刷新当前生效配置(热加载)。"""
    global minimax, azure, hermes
    minimax, azure, hermes = build(overrides)


def status() -> dict[str, bool]:
    return {"minimax": minimax.ready, "azure": azure.ready, "hermes": hermes.ready}
