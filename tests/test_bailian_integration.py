"""百炼 ASR 集成测试:有 key 才跑,无 key 自动跳过(不污染 CI)。"""
from pathlib import Path

import pytest

import config

SAMPLE = Path(__file__).resolve().parent.parent / "data/eval/sample.wav"

pytestmark = pytest.mark.skipif(
    not (config.bailian.ready and SAMPLE.exists()),
    reason="未配置 DASHSCOPE_API_KEY 或缺 sample.wav,跳过真实链路测试",
)


def test_bailian_transcribes_sample():
    from ai.bailian_asr import BailianASRProvider

    text = BailianASRProvider(config.bailian).transcribe(str(SAMPLE))
    assert "paris" in text.lower()
