"""自对弈验证:两个 AI 在一个场景里互相问答,跑通对话→纠错→课后总结。

一个 AI 演场景角色(用现有 ConversationEngine,如面试官);另一个 AI 扮英语学习者
(故意带点真实错误,用来检验纠错)。无真实人声,发音评测如实跳过(不编分)。
末尾用一个"评委"模型给对话自然度与纠错准确度打分(可量化效果)。

用法:
    python scripts/selfplay.py [scenario] [turns] [difficulty] [learner_level]
    例:python scripts/selfplay.py interview 4 2 A2
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai import ChatMessage, get_service  # noqa: E402
from conversation import ConversationEngine  # noqa: E402
from grammar import GrammarChecker  # noqa: E402
from jsonutil import extract_json_object  # noqa: E402
from report import ReportGenerator  # noqa: E402
from scenarios import get_scenario  # noqa: E402

C = {"tutor": "\033[36m", "learner": "\033[33m", "fix": "\033[31m",
     "ok": "\033[32m", "dim": "\033[90m", "end": "\033[0m", "b": "\033[1m"}


def c(key: str, text: str) -> str:
    return f"{C[key]}{text}{C['end']}"


class LearnerAgent:
    """扮演英语学习者:简短作答,带 CEFR 级别相称的真实错误。"""

    def __init__(self, ai, scenario, level: str) -> None:
        self.ai = ai
        self.level = level
        self.system = (
            f"You are role-playing an English LEARNER (CEFR {level}, a Chinese "
            f"speaker) practicing a '{scenario.name}' conversation. You are the "
            f"USER being interviewed/served, not the host.\n"
            "Reply in 1-2 short sentences, naturally, staying in role.\n"
            "Make OCCASIONAL realistic mistakes a learner at this level makes "
            "(tense, articles, prepositions, word choice) — not every sentence, "
            "just natural slips. Output ONLY your spoken reply, no quotes/notes."
        )
        self.history: list[ChatMessage] = []  # 学习者视角:tutor=user, self=assistant

    def reply(self, tutor_msg: str) -> str:
        self.history.append(ChatMessage("user", tutor_msg))
        out = self.ai.chat(self.history, system=self.system, max_tokens=600).strip()
        self.history.append(ChatMessage("assistant", out))
        return out


def judge(ai, scenario_name, transcript: str) -> dict | None:
    prompt = (
        f"Below is a role-play '{scenario_name}' conversation between an English "
        "tutor (host) and a learner. Rate it as STRICT JSON only:\n"
        '{"naturalness": 1-5, "tutor_in_role": 1-5, "comment": "one short line"}\n'
        "naturalness = how natural/coherent the dialogue is; tutor_in_role = "
        "how well the host stays in character.\n\n" + transcript
    )
    for budget in (2048, 4096):
        data = extract_json_object(ai.chat([ChatMessage("user", prompt)],
                                           max_tokens=budget))
        if data:
            return data
    return None


def main() -> int:
    scenario_key = sys.argv[1] if len(sys.argv) > 1 else "interview"
    turns = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    difficulty = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    level = sys.argv[4] if len(sys.argv) > 4 else "A2"

    ai = get_service()
    scenario = get_scenario(scenario_key)
    engine = ConversationEngine(ai=ai)
    grammar = GrammarChecker(ai=ai)
    reporter = ReportGenerator(ai=ai)
    learner = LearnerAgent(ai, scenario, level)

    print(c("b", f"\n=== 自对弈:{scenario.name} · 难度L{difficulty} · 学习者{level} "
                  f"· {turns}轮 ==="))
    print(c("dim", f"对话LLM在线={ai.llm_live} 发音评测在线={ai.pron_live}"
                   "(自对弈无真实人声,发音评测跳过)\n"))

    session = engine.start(scenario_key, difficulty)
    tutor_msg = session.history[0].content
    print(c("tutor", f"🎙️ 考官: {tutor_msg}"))

    transcript = [f"Tutor: {tutor_msg}"]
    learner_utts: list[str] = []
    corrections: list[dict] = []

    for i in range(turns):
        # 学习者作答
        lt = learner.reply(tutor_msg)
        learner_utts.append(lt)
        transcript.append(f"Learner: {lt}")
        print(c("learner", f"🧑 学习者: {lt}"))

        # 纠错
        r = grammar.check(lt, level=level)
        if r.has_issues:
            for x in r.corrections:
                corrections.append(x.to_dict())
                print(f"   {c('fix', '✗ ' + x.original)} → {c('ok', x.corrected)} "
                      f"{c('dim', '· ' + x.reason)}")
        else:
            print(c("dim", "   ✓ 本句无明显问题"))

        # 考官回应
        tutor_msg = engine.reply(session, lt)
        transcript.append(f"Tutor: {tutor_msg}")
        print(c("tutor", f"🎙️ 考官: {tutor_msg}"))

    # 课后总结
    print(c("b", "\n=== 课后总结 ==="))
    summary = reporter.summarize(scenario=scenario_key, user_utterances=learner_utts,
                                 corrections=corrections, completed=True)
    print(c("ok", "优秀表达:"), summary.highlights or "—")
    print(c("fix", "高频错误:"), summary.frequent_errors or "—")
    print(c("ok", "推荐表达:"), summary.recommended or "—")
    print("训练建议:", summary.advice or "—")
    sk = summary.raw_skills.to_dict()
    print(c("dim", "六维(本次原始分,发音/流利无人声故为 None):"))
    print(c("dim", "   " + "  ".join(f"{k}={v}" for k, v in sk.items())))

    # 评委打分
    print(c("b", "\n=== 评委评分 ==="))
    verdict = judge(ai, scenario.name, "\n".join(transcript))
    if verdict:
        print(f"  自然度 {verdict.get('naturalness')}/5 · "
              f"考官在角色 {verdict.get('tutor_in_role')}/5")
        print(c("dim", "  " + str(verdict.get("comment", ""))))
    else:
        print(c("dim", "  (评委未返回有效评分)"))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
