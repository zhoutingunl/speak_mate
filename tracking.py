"""统一埋点 + 耗时测量(design.md §19)。

track(event, payload):落 events 表(用户行为采集)。
timed(metric):上下文管理器,用 perf_counter 测关键路径耗时,落 'latency' 事件,
供 /api/qos 聚合出真实 QoS(p50/p95/avg)。
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager

import db

log = logging.getLogger("speakmate.track")

# 约定事件名(design.md §19)
EVENTS = {
    "session_start", "session_finish", "voice_start", "voice_finish", "voice_error",
    "ai_reply", "ai_error", "grammar_fix", "pronunciation_fix", "suggestion_accept",
    "dashboard_open", "selfplay_run", "latency",
}


def track(event: str, payload: dict | None = None) -> None:
    """记录一次事件;失败不影响主流程。"""
    try:
        db.add_event(event, payload or {})
    except Exception as e:  # pragma: no cover - 埋点不应影响业务
        log.warning("track(%s) failed: %s", event, e)


@contextmanager
def timed(metric: str, extra: dict | None = None):
    """测量代码块耗时(毫秒)并落 latency 事件。

    用法:
        with timed("llm_first_token"):
            ...  # 关键路径
    block 内可通过 yield 出的 dict 追加字段。
    """
    info: dict = {}
    t0 = time.perf_counter()
    try:
        yield info
    finally:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        track("latency", {"metric": metric, "ms": ms, **(extra or {}), **info})


def mark(metric: str, ms: float, extra: dict | None = None) -> None:
    """直接记录一个已测得的耗时(用于流式首包等不便用 with 包裹的场景)。"""
    track("latency", {"metric": metric, "ms": round(ms, 1), **(extra or {})})
