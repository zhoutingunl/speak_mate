"""场景配置(design.md §5.1、§6)。

新增场景 = 加一份 Scenario,无需改对话引擎代码。难度 L1~L5 控制用词/句长/语速。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# 难度梯度提示(design.md §11),注入 system prompt
_DIFFICULTY = {
    1: "Use very simple words and short sentences. Speak slowly and clearly. CEFR A1.",
    2: "Use common everyday vocabulary and simple sentences. CEFR A2-B1.",
    3: "Use natural conversational English at a normal pace. CEFR B1-B2.",
    4: "Use richer vocabulary, idioms and longer sentences. CEFR B2-C1.",
    5: "Speak like a native professional, fast and nuanced. CEFR C1-C2.",
}


@dataclass(frozen=True)
class Scenario:
    key: str
    name: str          # 展示名
    role: str          # AI 扮演的角色
    goal: str          # 本场景训练目标(给用户看)
    opening: str       # AI 的开场白(用户进入即可见/听到)
    custom: bool = False  # 用户自定义(可删除)
    # 来源标注(诚实):builtin=内置,llm=LLM 真生成,mock=LLM 失败后的默认模板
    generated_by: Literal["builtin", "llm", "mock"] = "builtin"

    def system_prompt(self, difficulty: int = 2) -> str:
        level = _DIFFICULTY.get(difficulty, _DIFFICULTY[2])
        return (
            f"You are {self.role}. Stay in character for the whole conversation.\n"
            f"Scenario goal: {self.goal}\n"
            f"Difficulty: {level}\n"
            "Rules:\n"
            "- Have a natural back-and-forth conversation in English.\n"
            "- Ask one question at a time; keep your turns concise (1-3 sentences).\n"
            "- Do NOT correct the user's grammar mid-conversation; just keep the "
            "conversation flowing naturally (corrections are handled separately).\n"
            "- If the user goes silent or off-topic, gently guide them back.\n"
            "- Never break character or mention that you are an AI."
        )


SCENARIOS: dict[str, Scenario] = {
    "interview": Scenario(
        key="interview",
        name="求职面试",
        role="a professional but friendly job interviewer at a tech company",
        goal="Practice answering common job-interview questions fluently and confidently.",
        opening="Hi, thanks for coming in today. To start, could you tell me a little about yourself?",
    ),
    "restaurant": Scenario(
        key="restaurant",
        name="餐厅点餐",
        role="a warm waiter at a casual Western restaurant",
        goal="Practice ordering food, asking about the menu, and handling small talk while dining out.",
        opening="Good evening! Welcome. Have you had a chance to look at the menu, or can I get you started with something to drink?",
    ),
    "meeting": Scenario(
        key="meeting",
        name="商务会议",
        role="a friendly colleague leading a short project status meeting",
        goal="Practice giving project updates, sharing opinions, agreeing/disagreeing, and discussing next steps in a workplace meeting.",
        opening="Morning! Thanks for joining. Let's start with a quick update — how is your part of the project going so far?",
    ),
}


def get_scenario(key: str) -> Scenario:
    try:
        return SCENARIOS[key]
    except KeyError:
        raise ValueError(
            f"未知场景 {key!r};可用:{', '.join(SCENARIOS)}") from None


def register(scenario: Scenario) -> None:
    """注册/覆盖场景(用于加载自定义场景到内存注册表)。"""
    SCENARIOS[scenario.key] = scenario


def remove(key: str) -> None:
    """移除自定义场景(内置场景不可删)。"""
    sc = SCENARIOS.get(key)
    if sc and sc.custom:
        del SCENARIOS[key]
    else:
        raise ValueError("内置场景不可删除" if sc else f"场景不存在:{key}")
