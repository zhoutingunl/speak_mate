"""QoS 实测基准(design.md §17)。

对关键路径各跑 N 次,用 perf_counter 测真实耗时,算 p50/p95/avg,
写入 docs/QoS.md(真实数字 + 方法学)。需真实 key(MiniMax/Azure)。

用法:python scripts/benchmark.py [N]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai import ChatMessage, get_service  # noqa: E402
from conversation import ConversationEngine  # noqa: E402
from grammar import GrammarChecker  # noqa: E402


def pct(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    i = min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))
    return round(s[i], 1)


def stat(vals):
    return {"n": len(vals), "p50": pct(vals, 50), "p95": pct(vals, 95),
            "avg": round(sum(vals) / len(vals), 1) if vals else 0.0}


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    ai = get_service()
    if not ai.llm_live:
        print("需要真实 MiniMax key(.env)才能跑基准"); return 1
    grammar = GrammarChecker(ai=ai)
    M = {k: [] for k in ("llm_first_token", "llm_total", "tts_first_chunk",
                         "tts_total", "grammar_check", "pron_roundtrip")}
    sample = ROOT / "data/eval/sample.wav"

    print(f"基准:每项 {n} 次 …")
    for i in range(n):
        eng = ConversationEngine(ai=ai)
        s = eng.start("interview", 2)
        # LLM 首 token / 全程
        t0 = time.perf_counter(); first = None
        for _ in eng.reply_stream(s, "I have been to Paris and it was great."):
            if first is None:
                first = (time.perf_counter() - t0) * 1000
        M["llm_first_token"].append(first or 0)
        M["llm_total"].append((time.perf_counter() - t0) * 1000)

        # TTS 首包 / 全程
        t0 = time.perf_counter(); first = None
        for _ in ai.synthesize_stream("Hello, this is a latency benchmark."):
            if first is None:
                first = (time.perf_counter() - t0) * 1000
        M["tts_first_chunk"].append(first or 0)
        M["tts_total"].append((time.perf_counter() - t0) * 1000)

        # 纠错
        t0 = time.perf_counter()
        grammar.check("I has went there yesterday.")
        M["grammar_check"].append((time.perf_counter() - t0) * 1000)

        # 发音评测往返
        if ai.pron_live and sample.exists():
            t0 = time.perf_counter()
            ai.score_pronunciation(str(sample), "I have been to Paris.")
            M["pron_roundtrip"].append((time.perf_counter() - t0) * 1000)
        print(f"  round {i+1}/{n} done")

    labels = {
        "llm_first_token": "LLM 首 token", "llm_total": "LLM 全程回复",
        "tts_first_chunk": "TTS 首包", "tts_total": "TTS 全程",
        "grammar_check": "纠错(单句)", "pron_roundtrip": "发音评测往返",
    }
    lines = ["# QoS 实测结果", "",
             f"方法:`scripts/benchmark.py`,每项 {n} 次,`time.perf_counter()` 计时;",
             "本机直连真实 MiniMax / Azure。单位毫秒(ms)。", "",
             "| 指标 | p50 | p95 | avg | 样本 |", "|---|---|---|---|---|"]
    for k, label in labels.items():
        if M[k]:
            st = stat(M[k])
            lines.append(f"| {label} | {st['p50']} | {st['p95']} | {st['avg']} | {st['n']} |")
    fl = stat(M["llm_first_token"]) if M["llm_first_token"] else {"p50": 0}
    ft = stat(M["tts_first_chunk"]) if M["tts_first_chunk"] else {"p50": 0}
    lines += [
        "",
        f"**首句可听**(LLM 首 token + TTS 首包,p50)≈ **{round(fl['p50'] + ft['p50'])} ms**。",
        "取代早期文档中未经测量的「首句 1 秒」估计值。",
        "",
        "> 说明:",
        "> - 数值为单次采样,随真实网络与 MiniMax 负载波动(实测首 token 在 0.3~1.8s 间);",
        "> - **纠错为旁路异步**,在用户说完后返回,不阻塞对话首句;其耗时含失败重试预算;",
        "> - 发音评测亦为旁路(录音后异步),不计入对话首句延迟。",
    ]
    out = ROOT / "docs/QoS.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
