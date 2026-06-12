"""MiniMax 接入:文本对话(Anthropic 兼容)+ 流式 TTS(WebSocket t2a_v2)。

实测结论(design.md §9、记忆 speakmate-ai-stack):
- 对话:POST {base}/v1/messages,x-api-key 鉴权,可用。
- TTS:wss://{host}/ws/v1/t2a_v2,task_start→task_continue→音频分片,可用。
- MiniMax 不做音频输入/发音评测——本模块只负责对话与 TTS。
"""
from __future__ import annotations

import json
from collections.abc import Iterator

import requests

from config import MiniMaxConfig
from .types import ChatMessage


class MiniMaxError(RuntimeError):
    pass


class MiniMaxClient:
    def __init__(self, cfg: MiniMaxConfig, *, timeout: float = 30.0) -> None:
        if not cfg.ready:
            raise MiniMaxError("MiniMax API key 未配置")
        self.cfg = cfg
        self.timeout = timeout

    # ---------------- 对话 ----------------
    def _headers(self) -> dict:
        return {
            "x-api-key": self.cfg.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _payload(self, messages: list[ChatMessage], system: str | None,
                 max_tokens: int, stream: bool) -> dict:
        body: dict = {
            "model": self.cfg.llm_model,
            "max_tokens": max_tokens,
            "messages": [m.to_api() for m in messages],
        }
        if system:
            body["system"] = system
        if stream:
            body["stream"] = True
        return body

    def chat(self, messages: list[ChatMessage], *, system: str | None = None,
             max_tokens: int = 1024) -> str:
        """非流式对话,返回完整文本(忽略 thinking 块,只取 text)。"""
        resp = requests.post(
            f"{self.cfg.base_url}/v1/messages",
            headers=self._headers(),
            json=self._payload(messages, system, max_tokens, stream=False),
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise MiniMaxError(f"chat HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        parts = [b.get("text", "") for b in data.get("content", [])
                 if b.get("type") == "text"]
        return "".join(parts).strip()

    def chat_stream(self, messages: list[ChatMessage], *, system: str | None = None,
                    max_tokens: int = 1024) -> Iterator[str]:
        """流式对话,逐段产出正文 text_delta(供首句优先,见 design.md §8)。"""
        with requests.post(
            f"{self.cfg.base_url}/v1/messages",
            headers=self._headers(),
            json=self._payload(messages, system, max_tokens, stream=True),
            timeout=self.timeout,
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                raise MiniMaxError(
                    f"chat_stream HTTP {resp.status_code}: {resp.text[:300]}")
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    evt = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                if evt.get("type") == "content_block_delta":
                    delta = evt.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield text

    # ---------------- 流式 TTS ----------------
    def synthesize_stream(self, text: str, *, audio_format: str = "mp3",
                          sample_rate: int = 16000) -> Iterator[bytes]:
        """WebSocket 流式 TTS,逐片产出音频字节(边收边播,见 design.md §8)。"""
        # 延迟导入,未装 websocket-client 时不影响对话路径
        from websocket import create_connection

        url = f"wss://{self.cfg.api_host}/ws/v1/t2a_v2"
        ws = create_connection(
            url, header=[f"Authorization: Bearer {self.cfg.api_key}"],
            timeout=self.timeout,
        )
        try:
            self._ws_expect(ws, "connected_success")
            ws.send(json.dumps({
                "event": "task_start",
                "model": self.cfg.tts_model,
                "voice_setting": {"voice_id": self.cfg.tts_voice, "speed": 1,
                                   "vol": 1, "pitch": 0},
                "audio_setting": {"sample_rate": sample_rate, "bitrate": 128000,
                                   "format": audio_format, "channel": 1},
            }))
            self._ws_expect(ws, "task_started")
            ws.send(json.dumps({"event": "task_continue", "text": text}))
            while True:
                msg = json.loads(ws.recv())
                audio_hex = msg.get("data", {}).get("audio")
                if audio_hex:
                    yield bytes.fromhex(audio_hex)
                if msg.get("is_final") or msg.get("event") == "task_finished":
                    break
        finally:
            try:
                ws.send(json.dumps({"event": "task_finish"}))
            except Exception:
                pass
            ws.close()

    @staticmethod
    def _ws_expect(ws, event: str) -> dict:
        msg = json.loads(ws.recv())
        if msg.get("event") not in (event, None):
            # MiniMax 偶发不回 connected 事件,容忍 None;其余视为协议错误
            if msg.get("base_resp", {}).get("status_code", 0) != 0:
                raise MiniMaxError(f"TTS 协议错误,期望 {event},收到 {msg}")
        return msg
