"""用 Playwright + 本机 Chrome 截取真实运行截图,存到 docs/img/。

原则:截图全部来自真实接口(真 AI 回复、真 Azure 发音分),不编造数据。
前置:服务已在 http://127.0.0.1:5001 运行,且配置了 MiniMax/Azure key。

用法:python scripts/capture_screenshots.py
"""
from __future__ import annotations

import base64
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs/img"
SAMPLE = ROOT / "data/eval/sample.wav"
BASE = "http://127.0.0.1:5001"


def seed_dashboard() -> None:
    """通过真实接口跑几次会话,给 Dashboard 填充真实数据。

    - 对话/纠错用真实(含错)句子 → 真实纠错与错误分布;
    - 发音评测的参照文本对齐样本音频「I have been to Paris.」→ 真实且合理的高分。
    """
    audio = SAMPLE.read_bytes()
    ref = "I have been to Paris."
    turns = {
        "interview": ["I have been to Paris.",
                      "I has went there yesterday and I very like it."],
        "restaurant": ["Could I get a burger, please?",
                       "She don't have no time for dessert."],
    }
    for scen, texts in turns.items():
        sid = requests.post(f"{BASE}/api/session",
                            json={"scenario": scen, "difficulty": 2}).json()["session_id"]
        for t in texts:
            requests.post(f"{BASE}/api/chat", json={"session_id": sid, "text": t})
            requests.post(f"{BASE}/api/correct", json={"session_id": sid, "text": t})
            requests.post(f"{BASE}/api/pronounce",
                          files={"audio": ("s.wav", audio, "audio/wav")},
                          data={"ref_text": ref, "session_id": sid})
        requests.post(f"{BASE}/api/report", json={"session_id": sid})
        print(f"  seeded session: {scen}")


def main() -> int:
    from playwright.sync_api import sync_playwright

    IMG.mkdir(parents=True, exist_ok=True)
    print("seeding dashboard via real API …")
    seed_dashboard()

    wav_b64 = base64.b64encode(SAMPLE.read_bytes()).decode()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1040, "height": 880},
                                device_scale_factor=2)

        # 1) 场景选择
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_selector(".scenario")
        page.screenshot(path=str(IMG / "01-scenarios.png"),
                        clip={"x": 0, "y": 0, "width": 1040, "height": 720})
        print("  shot 01-scenarios")

        # 2) 实时对话 + 反馈(驱动真实一轮:真 AI 回复 + 真 Azure 发音 + 真纠错)
        page.evaluate(
            """async (wavB64) => {
                document.querySelector('.scenario').click();
                await startSession();
                const bin = atob(wavB64); const arr = new Uint8Array(bin.length);
                for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
                const blob = new Blob([arr], { type: 'audio/wav' });
                state.pronLive = true;
                await processTurn('I have been to Paris.', blob);
                await processTurn('I has went there yesterday and I very like it.', null);
            }""",
            wav_b64,
        )
        # 等真实卡片渲染完成:发音分(.score-row)与纠错(.fix)都出现
        page.wait_for_selector(".feedback .score-row", timeout=30000)
        page.wait_for_selector(".feedback .fix", timeout=30000)
        time.sleep(3)
        page.screenshot(path=str(IMG / "02-conversation.png"), full_page=True)
        print("  shot 02-conversation")

        # 3) Dashboard
        page.goto(f"{BASE}/dashboard", wait_until="networkidle")
        page.wait_for_selector("#radar svg")
        time.sleep(1.5)
        page.screenshot(path=str(IMG / "03-dashboard.png"), full_page=True)
        print("  shot 03-dashboard")

        # 4) 设置(Key 打码)
        page.goto(f"{BASE}/settings", wait_until="networkidle")
        page.wait_for_selector(".set-row")
        time.sleep(1)
        page.screenshot(path=str(IMG / "04-settings.png"), full_page=True)
        print("  shot 04-settings")

        browser.close()
    print("done ->", IMG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
