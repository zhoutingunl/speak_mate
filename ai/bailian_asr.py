"""百炼(DashScope)Paraformer ASR —— 浏览器 Web Speech 的服务端兜底(design.md §9)。

输入 16k 单声道 WAV,返回转写文本。供 Safari/Firefox 默认使用,Chrome/Edge 可选。
无 key 时不实例化(由 AIService 决定降级)。
"""
from __future__ import annotations

from config import BailianConfig


class BailianASRError(RuntimeError):
    pass


class BailianASRProvider:
    def __init__(self, cfg: BailianConfig) -> None:
        if not cfg.ready:
            raise BailianASRError("DASHSCOPE_API_KEY 未配置")
        self.cfg = cfg

    def transcribe(self, wav_path: str, *, language: str = "en") -> str:
        import dashscope
        from dashscope.audio.asr import Recognition

        recognition = Recognition(
            model=self.cfg.asr_model,
            format="wav",
            sample_rate=16000,
            language_hints=[language],
            callback=None,
            api_key=self.cfg.api_key,
        )
        result = recognition.call(wav_path)
        if result.status_code != 200:
            raise BailianASRError(
                f"百炼 ASR {result.status_code}: {getattr(result, 'message', '')}")
        return self._join(result.output)

    @staticmethod
    def _join(output: dict | None) -> str:
        if not output:
            return ""
        sentences = output.get("sentence") or output.get("sentences") or []
        return " ".join(s.get("text", "").strip()
                        for s in sentences if s.get("text")).strip()
