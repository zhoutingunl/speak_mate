"""从 LLM 输出里稳健地抽取 JSON 对象。

LLM 常把 JSON 包在 ```json fence 里,或前后带 thinking/解释文字。
统一在这里处理,grammar / report 等结构化输出模块共用。
"""
from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def extract_json_object(raw: str) -> dict | None:
    """返回第一个能解析成 dict 的 JSON;失败返回 None。"""
    if not raw:
        return None
    fenced = _FENCE.search(raw)
    if fenced:
        candidate = fenced.group(1)
    else:
        start, end = raw.find("{"), raw.rfind("}")
        candidate = raw[start:end + 1] if 0 <= start < end else ""
    if not candidate:
        return None
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
