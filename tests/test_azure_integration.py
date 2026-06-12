"""Azure 发音评测集成测试:有 key 才跑,无 key 自动跳过(不污染 CI)。

验证真实音素级评测链路;单测用 Mock 不打接口,这里是补充的真实链路冒烟。
"""
from pathlib import Path

import pytest

import config

SAMPLE = Path(__file__).resolve().parent.parent / "data/eval/sample.wav"

pytestmark = pytest.mark.skipif(
    not (config.azure.ready and SAMPLE.exists()),
    reason="未配置 AZURE_SPEECH_KEY 或缺 sample.wav,跳过真实链路测试",
)


def test_azure_scores_clean_sample():
    from ai.azure_pron import AzurePronProvider

    score = AzurePronProvider(config.azure).score(
        str(SAMPLE), "I have been to Paris.")
    assert score.source == "azure" and not score.degraded
    assert "paris" in score.transcript.lower()
    # 合成的清晰样本应拿高分
    assert score.overall >= 70
    assert 0 <= score.pronunciation <= 100
    assert score.words and all(w.word for w in score.words)
