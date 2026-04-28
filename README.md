# Human-OS Engine 3.0

**基于分层架构 + LangGraph 的多场景对话引擎（README 与当前代码对齐版）**

[![Python >=3.11](https://img.shields.io/badge/python-%3E%3D3.11-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-75%20files-brightgreen.svg)](tests/)
[![Scenes](https://img.shields.io/badge/scenes-4-orange.svg)](skills/)
[![API](https://img.shields.io/badge/api-OpenAI%20Compatible-green.svg)](api/)

## 简介

这个项目是一个“多场景对话策略引擎”。  
核心思路是：把用户输入放进 Step0~Step9 的固定流程里，结合场景配置、策略组合、武器选择和记忆检索，最后输出一条可展示的话术。

当前仓库代码版本是 **3.0**（`pyproject.toml`、`main.py`、`api/routes.py` 均为 3.0）。

## 文档入口（先看这个顺序）

1. [SOURCE_OF_TRUTH.md](/C:/Users/youzi/Desktop/zixihecha/ninv/human-os-engine/docs/00_governance/SOURCE_OF_TRUTH.md)（谁说了算）
2. [PROJECT_TRUTH_MAP.md](/C:/Users/youzi/Desktop/zixihecha/ninv/human-os-engine/docs/01_active/PROJECT_TRUTH_MAP.md)（当前真源速查）
3. [NAVIGATION.md](/C:/Users/youzi/Desktop/zixihecha/ninv/human-os-engine/docs/01_active/NAVIGATION.md)（代码地图）

## 当前代码已实现

- Step0~Step9 主链路，当前是固定顺序执行（`step0 -> step1 -> step1_5 -> step2 -> step3 -> step4 -> step5 -> step6 -> step7 -> step8 -> step9`）。
- L1~L5 分层模块（优先级/识别/策略/执行/技能与评估）。
- Step2 已把目标拆成 `surface_goal / active_goal / underlying_goal` 三层写入 `Context`。
- Step3 已把趋势、压力、崩塌阶段这些判断沉到 `Context.self_check`。
- Step6 已产出 `do_now / do_later / avoid_now / fallback_move` 的策略骨架。
- Step8 已按骨架和稳定模板控制最终成品，并保留 `output_layers`。
- 评测入口 `simulation/run_eval_set.py` 默认按 `repeats=3` 中位数跑，`eval_report.json` 会带 `failure_code_distribution`。
- OpenAI 兼容接口：`/v1/models`、`/v1/chat/completions`（支持 stream）。
- 原生接口：`/health`、`/chat`、`/chat/stream`、`/sessions`（查询/删除）。
- 流式输出只对外发送“最终定稿文本分块”，不暴露中间推理字段。
- 会话持久化（SQLite）+ 过期清理 + 最大会话数驱逐。
- 记忆检索链路：**向量检索（ChromaDB） -> 关键词 fallback**。
- 场景识别：**LLM 语义分 + 关键词分融合**，并带缓存与仲裁逻辑。

## 已知边界（按当前代码）

- 默认场景是固定白名单：`sales / emotion / negotiation / management`。  
  场景配置默认从 `skills/` 加载，新增一个全新 `skills/*` 目录后，不改代码时不能直接作为默认可加载场景使用（受 `SceneLoader.ALLOWED_SCENES` 限制）。
- `SkillRegistry` 是全局单例，目录扫描发生在首次初始化。  
  运行中新增技能目录后，默认不会自动重新扫描。
- README 不再写“xx/xx 全通过”这类实时结果，测试请以你本地 `pytest` 为准。

## 执行流程

```text
用户输入
  -> Step0 输入处理
  -> Step1 识别
  -> Step1.5 元控制器
  -> Step2 场景与目标检测
  -> Step3 自检
  -> Step4 优先级
  -> Step5 模式选择
  -> Step6 策略生成
  -> Step7 武器选择
  -> Step8 执行与收口
  -> Step9 反馈与经验记录
```

分支规则（简化）：
- 在 `graph/streaming_pipeline.py` 这条兼容执行路径里：
  - Step0 命中快速路径可提前收口到 Step8。
  - Step1 低置信度可提前收口到 Step8。
  - Step3 触发崩塌保护可提前收口到 Step9。
- 主图 `graph/builder.py` 本身仍是固定顺序主链，不靠条件边跳步。

## 目录结构（与当前仓库一致）

```text
human-os-engine/
├── main.py
├── api/
│   ├── routes.py
│   ├── openai_adapter.py
│   └── session_store.py
├── graph/
│   ├── builder.py
│   ├── streaming_pipeline.py
│   └── nodes/
│       ├── step0_input.py ... step9_feedback.py
│       ├── helpers.py
│       ├── strategy_selector.py
│       ├── persona_checker.py
│       └── style_adapter.py
├── modules/
│   ├── L1/ L2/ L3/ L4/ L5/
│   └── memory.py
├── schemas/
├── llm/
├── prompts/
├── config/
├── skills/
│   ├── sales/
│   ├── emotion/
│   ├── negotiation/
│   └── management/
├── simulation/
├── scripts/
├── tests/
└── data/
```

## 环境要求

- Python `>=3.11`（项目声明）
- 至少配置一种可用 LLM Key（NVIDIA 或 DeepSeek）

## 安装

```bash
git clone <your-repo-url>
cd human-os-engine
pip install -e ".[api,test]"
```

## 配置（`.env`）

```env
# NVIDIA（可选，多 Key 用逗号分隔）
NVIDIA_API_KEYS=key1,key2
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1

# DeepSeek
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# 可选第二套 DeepSeek Key（降级链路会用）
DEEPSEEK_OFFICIAL_API_KEY=sk-xxx
DEEPSEEK_OFFICIAL_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_OFFICIAL_MODEL=deepseek-chat

# 管理接口鉴权（不填则 /sessions 管理端点不可用）
ADMIN_API_KEY=your-admin-token
```

## 运行

```bash
# 交互模式
py -3.13 main.py

# API 模式
py -3.13 main.py --api --port 8000
```

如果你不是 Windows，也可以用：

```bash
python main.py
python main.py --api --port 8000
```

## API 快速说明

### 原生接口

- `GET /health`
- `POST /chat`
- `POST /chat/stream`
- `GET /sessions`（需要 `Authorization: Bearer <ADMIN_API_KEY>` 或 `X-Admin-Token`）
- `DELETE /sessions/{session_id}`（同上）
- `GET /admin/memory/write-summary/{session_id}`（同上，单会话记忆写入观测）
- `GET /admin/memory/write-summary-global`（同上，全局记忆写入观测）

### OpenAI 兼容接口

- `GET /v1/models`
- `POST /v1/chat/completions`

`/v1/models` 当前返回模型 ID：`human-os-3.0`。

## 运维排查入口（常用）

1. 记忆排查操作卡：  
[MEMORY_OBSERVABILITY_GUIDE.md](/C:/Users/youzi/Desktop/zixihecha/ninv/human-os-engine/docs/01_active/MEMORY_OBSERVABILITY_GUIDE.md)
2. 评测排查操作卡：  
[EVAL_OBSERVABILITY_GUIDE.md](/C:/Users/youzi/Desktop/zixihecha/ninv/human-os-engine/docs/01_active/EVAL_OBSERVABILITY_GUIDE.md)
3. 门禁总览解读卡：  
[GUARD_OVERVIEW_GUIDE.md](/C:/Users/youzi/Desktop/zixihecha/ninv/human-os-engine/docs/01_active/GUARD_OVERVIEW_GUIDE.md)
4. 这轮大跑复盘：  
[LARGE_SCALE_TEST_RECAP_20260417.md](/C:/Users/youzi/Desktop/zixihecha/ninv/human-os-engine/docs/01_active/LARGE_SCALE_TEST_RECAP_20260417.md)
5. 单会话记忆观测接口：  
`GET /admin/memory/write-summary/{session_id}?limit=50`
6. 全局记忆观测接口：  
`GET /admin/memory/write-summary-global?limit_per_user=50`

## OpenAI 流式请求示例

```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "human-os-3.0",
    "messages": [{"role": "user", "content": "你好，我最近工作压力很大"}],
    "stream": true
  }'
```

## 测试与模拟

```bash
# 全量测试（耗时可能较长）
py -3.13 -m pytest tests -v

# 只做收集（不执行）
py -3.13 -m pytest tests --collect-only -q
```

常用模拟命令：

```bash
py -3.13 simulation/arena_v2.py --runs 3 --max-rounds 5
py -3.13 simulation/sandbox_v2.py --scene sales --rounds 5 --regression
py -3.13 simulation/ab_test_runner.py
```

## README 自检（建议改动后执行）

下面这几个点最容易漂移，建议每次发版前核对：

1. 版本号是否一致：`README`、`pyproject.toml`、`main.py`、`api/routes.py`。  
2. Python 要求是否一致：`README` 和 `pyproject.toml`。  
3. API 路径是否一致：`README` 和 `api/routes.py`、`api/openai_adapter.py`。  
4. 场景列表是否一致：`README` 和 `skills/` + `SceneLoader.ALLOWED_SCENES`。  
5. 测试信息是否写成“固定通过数”（建议避免写死）。  

## 许可证

MIT License
