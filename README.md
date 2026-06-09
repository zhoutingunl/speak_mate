# SpeakMate — AI 英语口语陪练

在指定场景(面试 / 点餐 / 会议 …)下进行真实英语对话训练,提供**实时语音对话、发音评测、语法/表达纠错、课后总结与成长分析**。

完整设计见 [`design.md`](design.md)。

## 技术栈

| 能力 | 方案 |
|---|---|
| 对话 LLM | MiniMax(Anthropic 兼容端点) |
| TTS(AI 开口) | MiniMax 流式 TTS(WebSocket) |
| ASR(用户语音→文本) | 浏览器 Web Speech API |
| 发音评测 | Azure Pronunciation Assessment(音素级 GOP) |
| 后端 | Python 3.11 + Flask + gevent + SQLite |

## 快速开始

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # 填入你的 key(.env 已被 gitignore)
python scripts/check_connectivity.py   # 各外部依赖各打一发真实请求自检
pytest -q                 # 运行单测(走 Mock,不需要任何 key)
```

> **无 key 也能跑**:未配置某项 key 时,该能力自动进入 Mock/降级模式并明确标注,
> 不会崩溃——方便在没有凭证时体验与评审。

### 需要的 key

- `MINIMAX_API_KEY` — 对话与 TTS([platform.minimaxi.com](https://platform.minimaxi.com))
- `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` — 发音评测(Azure Speech 有免费额度)

## 当前进度

- [x] 接入层骨架:`AIService` 统一入口 + MiniMax 对话/TTS + Azure 发音评测(**三条线均实测连通**)+ Mock/降级
- [x] 对话引擎与场景配置:`conversation.py` + Interview/Restaurant 场景,流式回复、上下文窗口、L1~L5 难度(实测多轮对话在角色内)
- [x] 语法/表达纠错:`grammar.py` 延迟纠错,结构化「错误句→原因→推荐」,LLM 解析失败自动重试再降级规则(实测纠错精准)
- [x] 课后总结 + 六维能力模型:`report.py` 总结(优秀表达/高频错误/推荐/建议)+ `skills.py` EWMA 更新;声学维度无数据时置 None 不臆造
- [ ] WebSocket 实时语音通道(前端录音 + 流式播放)
- [ ] Flask 应用 + 前端页面
- [ ] Dashboard

## AI 协作说明

本项目开发中使用了 AI 辅助工具(Claude Code 等),如实声明:

- **运行时 AI 能力**:对话/纠错/总结 = MiniMax(主)/ Hermes(兜底);TTS = MiniMax 流式;
  ASR = 浏览器 Web Speech API;发音评测 = Azure Pronunciation Assessment。
- **选型有据**:发音评测最初设想用 MiniMax 多模态,经**实测确认其聊天端点收不到音频、
  且无发音评测产品**后改接 Azure(音素级)。决策与证据见 `design.md` §9/§12。
- **承诺**:提交的功能均可运行、测试真实通过;README/demo 所述能力与代码一致,
  不伪造功能、不伪造测试与演示;走降级/Mock 处,文档与 UI 均如实标注。
