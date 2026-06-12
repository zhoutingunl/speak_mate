"""AI 接入层。业务代码只依赖 AIService(见 design.md §9),禁止直连模型。"""
from .service import AIService, get_service
from .types import ChatMessage, PronScore, WordScore

__all__ = ["AIService", "get_service", "ChatMessage", "PronScore", "WordScore"]
