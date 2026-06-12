"""对话引擎(design.md §11)。

维护会话状态、上下文窗口与难度,把场景 + 历史拼成 prompt 交给 AIService,
对外提供流式回复(首句优先,见 design.md §8)。本期会话存内存,
SessionStore 抽象留好以便后续 PR 接 SQLite。
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

from ai import AIService, ChatMessage, get_service
from scenarios import Scenario, get_scenario

# 上下文窗口:保留最近 N 轮(一问一答=2 条),design.md §11
CONTEXT_TURNS = 10
MAX_HISTORY_MESSAGES = CONTEXT_TURNS * 2


@dataclass
class Session:
    id: str
    scenario_key: str
    difficulty: int
    history: list[ChatMessage] = field(default_factory=list)  # 不含 system

    @property
    def scenario(self) -> Scenario:
        return get_scenario(self.scenario_key)

    def turns(self) -> int:
        """已完成的用户轮次数。"""
        return sum(1 for m in self.history if m.role == "user")


class SessionStore:
    """内存会话存储。后续 PR 可换成 SQLite 实现,接口不变。"""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def save(self, s: Session) -> None:
        self._sessions[s.id] = s

    def get(self, sid: str) -> Session:
        try:
            return self._sessions[sid]
        except KeyError:
            raise ValueError(f"会话不存在:{sid}") from None


class ConversationEngine:
    def __init__(self, ai: AIService | None = None,
                 store: SessionStore | None = None) -> None:
        self.ai = ai or get_service()
        self.store = store or SessionStore()

    def start(self, scenario_key: str, difficulty: int = 2) -> Session:
        """开启会话;AI 开场白预置进历史(用户一进来就有话说)。"""
        scenario = get_scenario(scenario_key)
        if not 1 <= difficulty <= 5:
            raise ValueError("difficulty 必须在 1~5")
        session = Session(
            id=uuid.uuid4().hex,
            scenario_key=scenario_key,
            difficulty=difficulty,
            history=[ChatMessage("assistant", scenario.opening)],
        )
        self.store.save(session)
        return session

    def reply_stream(self, session: Session, user_text: str) -> Iterator[str]:
        """追加用户发言,流式产出 AI 回复;结束后把完整回复写回历史。"""
        user_text = (user_text or "").strip()
        if not user_text:
            raise ValueError("用户发言为空")
        session.history.append(ChatMessage("user", user_text))

        system, messages = self._build_prompt(session)
        collected: list[str] = []
        for chunk in self.ai.chat_stream(messages, system=system):
            collected.append(chunk)
            yield chunk

        reply = "".join(collected).strip()
        session.history.append(ChatMessage("assistant", reply))
        self._trim(session)
        self.store.save(session)

    def reply(self, session: Session, user_text: str) -> str:
        """非流式版本,便于测试/同步调用。"""
        return "".join(self.reply_stream(session, user_text)).strip()

    # ---- 内部 ----
    def _build_prompt(self, session: Session) -> tuple[str, list[ChatMessage]]:
        system = session.scenario.system_prompt(session.difficulty)
        # 历史已按窗口裁剪,直接作为对话消息
        return system, list(session.history)

    @staticmethod
    def _trim(session: Session) -> None:
        if len(session.history) > MAX_HISTORY_MESSAGES:
            # 保留最近 N 轮;首条开场白可丢弃(系统提示已含场景设定)
            session.history = session.history[-MAX_HISTORY_MESSAGES:]
