"""自对弈核心(design.md §18):两个 AI 在同一场景互问互答。

一个 AI 用 ConversationEngine 演场景角色;一个 AI 扮 CEFR 学习者(带真实错误)。
run_selfplay 以事件流逐步产出,CLI 与 Web SSE 共用。无真实人声 → 不做发音评测。
"""
from __future__ import annotations

from collections.abc import Iterator

from ai import AIService, ChatMessage
from conversation import ConversationEngine
from grammar import GrammarChecker
from jsonutil import extract_json_object
from report import ReportGenerator
from scenarios import Scenario, get_scenario


class LearnerAgent:
    """扮演英语学习者:简短作答,带 CEFR 级别相称的真实错误。"""

    def __init__(self, ai: AIService, scenario: Scenario, level: str) -> None:
        self.ai = ai
        self.system = (
            f"You are role-playing an English LEARNER (CEFR {level}, a Chinese "
            f"speaker) practicing a '{scenario.name}' conversation. You are the "
            f"USER being interviewed/served, not the host.\n"
            "Reply in 1-2 short sentences, naturally, staying in role.\n"
            "Make OCCASIONAL realistic mistakes a learner at this level makes "
            "(tense, articles, prepositions, word choice) — not every sentence, "
            "just natural slips. Output ONLY your spoken reply, no quotes/notes."
        )
        self.history: list[ChatMessage] = []

    def reply(self, tutor_msg: str) -> str:
        self.history.append(ChatMessage("user", tutor_msg))
        out = self.ai.chat(self.history, system=self.system, max_tokens=600).strip()
        self.history.append(ChatMessage("assistant", out))
        return out


def judge(ai: AIService, scenario_name: str, transcript: str) -> dict | None:
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


def run_selfplay(ai: AIService, scenario_key: str, *, turns: int = 4,
                 difficulty: int = 2, level: str = "A2") -> Iterator[dict]:
    """逐步产出事件:start / tutor / learner / correction / summary / judge / done。"""
    scenario = get_scenario(scenario_key)
    turns = max(1, min(turns, 8))
    engine = ConversationEngine(ai=ai)
    grammar = GrammarChecker(ai=ai)
    reporter = ReportGenerator(ai=ai)
    learner = LearnerAgent(ai, scenario, level)

    yield {"type": "start", "scenario": scenario.name, "turns": turns,
           "difficulty": difficulty, "level": level}

    session = engine.start(scenario_key, difficulty)
    tutor_msg = session.history[0].content
    yield {"type": "tutor", "text": tutor_msg}

    transcript = [f"Tutor: {tutor_msg}"]
    learner_utts: list[str] = []
    corrections: list[dict] = []

    for _ in range(turns):
        lt = learner.reply(tutor_msg)
        learner_utts.append(lt)
        transcript.append(f"Learner: {lt}")
        yield {"type": "learner", "text": lt}

        result = grammar.check(lt, level=level)
        if result.has_issues:
            items = [x.to_dict() for x in result.corrections]
            corrections.extend(items)
            yield {"type": "correction", "items": items, "polished": result.polished}

        tutor_msg = engine.reply(session, lt)
        transcript.append(f"Tutor: {tutor_msg}")
        yield {"type": "tutor", "text": tutor_msg}

    summary = reporter.summarize(scenario=scenario_key, user_utterances=learner_utts,
                                 corrections=corrections, completed=True)
    yield {"type": "summary", **summary.to_dict()}

    verdict = judge(ai, scenario.name, "\n".join(transcript))
    yield {"type": "judge", "verdict": verdict}
    yield {"type": "done"}
