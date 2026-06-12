"""Azure 发音评测(音素级 GOP)。见 design.md §12。

一次识别同时拿到转写 + Accuracy/Fluency/Completeness/Prosody + 逐词结果。
无 key 时不实例化(由 AIService 决定降级/Mock)。
"""
from __future__ import annotations

from config import AzureConfig
from .types import PronScore, WordScore


class AzurePronError(RuntimeError):
    pass


class AzurePronProvider:
    """PronunciationProvider 的 Azure 实现(design.md §12.3)。"""

    def __init__(self, cfg: AzureConfig) -> None:
        if not cfg.ready:
            raise AzurePronError("Azure Speech key/region 未配置")
        self.cfg = cfg

    def score(self, audio_path: str, ref_text: str) -> PronScore:
        # 延迟导入:未安装 SDK 时不影响其它路径
        import azure.cognitiveservices.speech as speechsdk

        speech_cfg = speechsdk.SpeechConfig(
            subscription=self.cfg.api_key, region=self.cfg.region)
        audio_cfg = speechsdk.audio.AudioConfig(filename=audio_path)

        pa_cfg = speechsdk.PronunciationAssessmentConfig(
            reference_text=ref_text,
            grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
            granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
            enable_miscue=True,
        )
        pa_cfg.enable_prosody_assessment()

        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_cfg, audio_config=audio_cfg)
        pa_cfg.apply_to(recognizer)
        result = recognizer.recognize_once()

        if result.reason != speechsdk.ResultReason.RecognizedSpeech:
            raise AzurePronError(f"Azure 识别失败:{result.reason}")

        return self._parse(result, speechsdk)

    @staticmethod
    def _parse(result, speechsdk) -> PronScore:
        pa = speechsdk.PronunciationAssessmentResult(result)
        prosody = getattr(pa, "prosody_score", None) or 0.0
        words = [
            WordScore(
                word=w.word,
                accuracy=round(w.accuracy_score, 1),
                error_type=getattr(w, "error_type", "None"),
            )
            for w in (pa.words or [])
        ]
        overall = PronScore.weighted(
            pa.accuracy_score, pa.fluency_score, prosody, pa.completeness_score)
        return PronScore(
            pronunciation=round(pa.accuracy_score, 1),
            fluency=round(pa.fluency_score, 1),
            prosody=round(prosody, 1),
            completeness=round(pa.completeness_score, 1),
            overall=overall,
            transcript=result.text,
            words=words,
            source="azure",
            degraded=False,
        )
