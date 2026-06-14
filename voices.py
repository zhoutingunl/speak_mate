"""MiniMax TTS 音色与语言目录(均已实测可用)。

供设置页(主训练 AI 音色)与自对弈页(考官/学习者音色)使用。
language_boost 用于多语言提示;"auto" 表示自动。
"""
from __future__ import annotations

VOICES: list[dict] = [
    {"id": "English_Trustworthy_Man", "name": "沉稳男声 (Trustworthy Man)", "lang": "English"},
    {"id": "English_Graceful_Lady", "name": "优雅女声 (Graceful Lady)", "lang": "English"},
    {"id": "English_ManWithDeepVoice", "name": "低沉男声 (Deep Voice)", "lang": "English"},
    {"id": "Wise_Woman", "name": "知性女声 (Wise Woman)", "lang": "English"},
    {"id": "English_Aussie_Bloke", "name": "澳洲男声 (Aussie Bloke)", "lang": "English"},
    {"id": "English_Diligent_Man", "name": "干练男声 (Diligent Man)", "lang": "English"},
    {"id": "English_Gentle-voiced_man", "name": "温柔男声 (Gentle Man)", "lang": "English"},
    {"id": "English_Whispering_girl", "name": "轻语女声 (Whispering Girl)", "lang": "English"},
    {"id": "Chinese (Mandarin)_Warm_Girl", "name": "中文·温暖女声", "lang": "Chinese"},
]

LANGUAGES: list[str] = [
    "auto", "English", "Chinese", "Japanese", "Korean", "Spanish", "French",
]

VOICE_IDS = {v["id"] for v in VOICES}
