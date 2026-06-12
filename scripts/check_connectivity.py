"""接入连通性自检:对每个外部依赖各打一发真实请求。

用法:
    python3.11 scripts/check_connectivity.py

无 key 的依赖会标记为 SKIP(并提示去 .env 配置),不算失败。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from ai.types import ChatMessage  # noqa: E402

OK, FAIL, SKIP = "✅ OK", "❌ FAIL", "— SKIP"


def check_minimax_llm() -> tuple[str, str]:
    if not config.minimax.ready:
        return SKIP, "未配置 MINIMAX_API_KEY"
    from ai.minimax import MiniMaxClient

    c = MiniMaxClient(config.minimax)
    out = c.chat([ChatMessage("user", "Say 'pong' and nothing else.")],
                 max_tokens=2000)
    return (OK, f"reply={out[:60]!r}") if out else (FAIL, "空回复")


def check_minimax_tts() -> tuple[str, str]:
    if not config.minimax.ready:
        return SKIP, "未配置 MINIMAX_API_KEY"
    from ai.minimax import MiniMaxClient

    c = MiniMaxClient(config.minimax)
    total = sum(len(chunk) for chunk in c.synthesize_stream("Hello there."))
    return (OK, f"收到音频 {total} 字节") if total > 0 else (FAIL, "无音频")


def check_azure() -> tuple[str, str]:
    if not config.azure.ready:
        return SKIP, "未配置 AZURE_SPEECH_KEY/REGION"
    sample = Path(__file__).resolve().parent.parent / "data/eval/sample.wav"
    if not sample.exists():
        return SKIP, "缺少样本音频 data/eval/sample.wav"
    from ai.azure_pron import AzurePronProvider

    score = AzurePronProvider(config.azure).score(
        str(sample), "I have been to Paris.")
    return OK, f"overall={score.overall} transcript={score.transcript!r}"


def main() -> int:
    print("== 配置就绪情况 ==", config.status())
    checks = [
        ("MiniMax LLM", check_minimax_llm),
        ("MiniMax TTS", check_minimax_tts),
        ("Azure 发音评测", check_azure),
    ]
    failed = False
    for name, fn in checks:
        try:
            status, detail = fn()
        except Exception as e:
            status, detail = FAIL, f"{type(e).__name__}: {e}"
        if status == FAIL:
            failed = True
        print(f"[{status}] {name:14} {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
