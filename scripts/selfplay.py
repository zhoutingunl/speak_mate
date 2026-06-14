"""自对弈验证(CLI):复用 selfplay.run_selfplay,彩色打印事件流。

用法:python scripts/selfplay.py [scenario] [turns] [difficulty] [learner_level]
    例:python scripts/selfplay.py interview 4 2 A2
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai import get_service  # noqa: E402
from selfplay import run_selfplay  # noqa: E402

C = {"tutor": "\033[36m", "learner": "\033[33m", "fix": "\033[31m",
     "ok": "\033[32m", "dim": "\033[90m", "end": "\033[0m", "b": "\033[1m"}


def c(key: str, text: str) -> str:
    return f"{C[key]}{text}{C['end']}"


def main() -> int:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "interview"
    turns = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    difficulty = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    level = sys.argv[4] if len(sys.argv) > 4 else "A2"

    ai = get_service()
    for ev in run_selfplay(ai, scenario, turns=turns, difficulty=difficulty,
                           level=level):
        t = ev["type"]
        if t == "start":
            print(c("b", f"\n=== 自对弈:{ev['scenario']} · 难度L{ev['difficulty']} "
                         f"· 学习者{ev['level']} · {ev['turns']}轮 ==="))
            print(c("dim", "(无真实人声,发音评测跳过)\n"))
        elif t == "tutor":
            print(c("tutor", f"🎙️ 考官: {ev['text']}"))
        elif t == "learner":
            print(c("learner", f"🧑 学习者: {ev['text']}"))
        elif t == "correction":
            for x in ev["items"]:
                print(f"   {c('fix', '✗ ' + x['original'])} → "
                      f"{c('ok', x['corrected'])} {c('dim', '· ' + x['reason'])}")
        elif t == "summary":
            print(c("b", "\n=== 课后总结 ==="))
            print(c("ok", "优秀表达:"), ev.get("highlights") or "—")
            print(c("fix", "高频错误:"), ev.get("frequent_errors") or "—")
            print(c("ok", "推荐表达:"), ev.get("recommended") or "—")
            print("训练建议:", ev.get("advice") or "—")
            sk = ev.get("raw_skills", {})
            print(c("dim", "六维(发音/流利无人声故 None):  "
                           + "  ".join(f"{k}={v}" for k, v in sk.items())))
        elif t == "judge":
            v = ev.get("verdict") or {}
            print(c("b", "\n=== 评委评分 ==="))
            print(f"  自然度 {v.get('naturalness', '?')}/5 · "
                  f"考官在角色 {v.get('tutor_in_role', '?')}/5")
            print(c("dim", "  " + str(v.get("comment", ""))))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
