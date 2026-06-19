# 自动生成工作周报助手

企业级研发周报 Agent：按配置定时采集 Git commit / PR / issue 与语雀文档更新，通过 LangChain 1.x 调用大模型生成结构化 Markdown 周报，并提供 FastAPI + Web UI 的结果展示、配置和导出能力。

> 说明：题目名称提到“每 2 分钟”，必选实现项提到“每分钟定时触发”。本项目采用可配置 Cron，示例配置默认每分钟触发；如需每 2 分钟触发，将 `schedule.cron` 改为 `*/2 * * * *`。

## 项目能力

- 可配置：通过 `config/example.yaml` 修改调度、数据源、LLM、模板、输出目录等行为。
- 自动触发：APScheduler 按 Cron 定时生成，示例默认每分钟。
- 自然周：所有周报固定采集当前自然周，即周一 00:00 到下周一 00:00，不使用“当前时间往前 7 天”。
- 数据源：接入 GitHub commit / PR / issue 与语雀文档更新。
- Agent 汇总：LangChain 1.x + ChatOpenAI 兼容接口，输出 `本周完成`、`进行中`、`风险/阻塞`、`下周计划`。
- 结果展示：Web UI 渲染 Markdown，支持手动触发与导出 `.md` 文件。
- 可直接运行：未配置真实 Token 时使用演示数据；未配置模型 Key 时使用本地兜底生成器。

## 技术栈

后端：

- Python 3.11+
- FastAPI：API 服务与静态页面托管
- APScheduler：Cron 定时任务
- LangChain 1.x：Prompt、LLM 调用与输出编排
- langchain-openai 1.x：OpenAI / OpenAI-compatible 模型接入
- Pydantic 2.x：配置与接口模型校验
- httpx：GitHub / 语雀 API 调用
- PyYAML：YAML 配置加载与保存

前端：

- 原生 HTML / CSS / JavaScript
- marked.js：浏览器端 Markdown 渲染
- Fetch API：调用 FastAPI 后端

## 目录结构

```text
report_ai/
├── README.md
├── requirements.txt
├── config/
│   └── example.yaml
├── docs/
│   └── design.md
├── reports/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── scheduler.py
│   ├── agent/
│   │   ├── __init__.py
│   │   └── weekly_report_agent.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── report_service.py
│   └── sources/
│       ├── __init__.py
│       ├── git_source.py
│       └── yuque_source.py
└── web/
    ├── index.html
    ├── styles.css
    └── app.js
```

## 安装步骤

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置说明

示例配置位于 `config/example.yaml`，可直接运行。敏感字段支持 `${ENV_NAME}` 形式从环境变量读取。

```bash
export GIT_TOKEN="ghp_xxx"
export YUQUE_TOKEN="xxx"
export OPENAI_API_KEY="sk_xxx"
```

关键字段：

| 字段 | 说明 |
| --- | --- |
| `schedule.cron` | Cron 表达式，示例默认 `* * * * *` 每分钟执行；时区由服务运行环境统一决定 |
| `sources.git.enabled` | 是否启用 Git 数据源 |
| `sources.git.provider` | Git 提供方，当前代码实现 `github`，预留 `gitlab` 适配 |
| `sources.git.api_base_url` | GitHub API 地址，企业版可替换 |
| `sources.git.token` | Git API Token |
| `sources.git.repos` | 仓库列表，例如 `org/repo-a` |
| `sources.git.include` | 是否采集 commits、pull_requests、issues |
| `sources.yuque.enabled` | 是否启用语雀数据源 |
| `sources.yuque.token` | 语雀 API Token |
| `sources.yuque.namespace` | 语雀知识库路径，例如 `team/project` |
| `llm.model` | LLM 模型名 |
| `llm.api_key` | 模型 API Key，未配置时启用本地兜底生成 |
| `llm.base_url` | OpenAI-compatible API 地址 |
| `report.template` | 自定义 Markdown 模板内容，支持 `{done}`、`{in_progress}`、`{risks}`、`{next_week}` 等占位符 |
| `report.sections` | 输出章节，必须包含 `done`、`in_progress`、`risks`、`next_week` |
| `report.output_dir` | Markdown 输出目录 |
| `web.enable_export` | 是否允许导出最新 Markdown |

## 启动命令

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

访问页面：

```text
http://localhost:8000
```

常用 API：

| API | 方法 | 说明 |
| --- | --- | --- |
| `/api/health` | GET | 健康检查 |
| `/api/config` | GET | 获取当前配置 |
| `/api/config` | POST | 保存页面配置并重载定时任务 |
| `/api/reports/generate` | POST | 手动触发生成 |
| `/api/reports/latest` | GET | 获取最新 Markdown |
| `/api/reports/export` | GET | 导出最新 Markdown 文件 |

## 真实 Git 环境测试

项目提供独立连通性脚本，可在启动 Web 前先验证 GitHub commit / PR / issue 是否能被真实采集：

```bash
python scripts/test_git_connection.py --repo microsoft/vscode
```

私有仓库：

```bash
export GIT_TOKEN="你的 GitHub Token"
python scripts/test_git_connection.py --repo your-org/your-private-repo
```

GitHub Enterprise：

```bash
python scripts/test_git_connection.py \
  --repo your-org/your-repo \
  --api-base-url "https://github.example.com/api/v3"
```

完整步骤见 `docs/git-real-test.md`。

## AI 使用说明

Agent 输入为统一 `WorkItem`：

- Git commit：标题、作者、提交时间、仓库、commit URL。
- PR：标题、作者、状态、更新时间、PR URL。
- Issue：标题、作者、状态、标签、Issue URL。
- 语雀文档：标题、更新人、更新时间、文档 URL。

Agent 流程：

1. `ReportService` 根据配置调用 `GitSource` 与 `YuqueSource`。
2. `ReportService` 按服务器本地日期计算当前自然周窗口：周一 00:00 到下周一 00:00。
3. 数据源适配器只采集该自然周窗口内的数据，并归一化为 `WorkItem`。
4. `WeeklyReportAgent` 使用 LangChain 1.x 组装 Prompt、自定义模板和自然周边界后调用模型。
5. 模型不可用时使用本地兜底生成器，保证系统可演示、可验收。
6. Markdown 保存到 `reports/weekly-report-*.md`。
7. Web UI 调用 `/api/reports/latest` 渲染，调用 `/api/reports/export` 导出。

Prompt 约束：

- 输出必须是 Markdown。
- 本周范围必须严格等于当前自然周，禁止按最近 7 天理解。
- 必须包含 `本周完成`、`进行中`、`风险/阻塞`、`下周计划`。
- 不得编造数据源中不存在的事实。
- 对不确定事项使用“待确认 / 可能”表述。
- 尽量保留来源链接，便于审计追溯。

## 开发步骤

1. 骨架搭建：完成 `src`、`web`、`docs`、`config`、`requirements.txt`。
2. 配置系统：实现 YAML 加载、环境变量展开、页面保存和定时任务重载。
3. 数据源接入：实现 GitHub commit / PR / issue 与语雀文档列表采集。
4. Agent 生成：实现 LangChain Prompt、模型调用、章节兜底校验和本地兜底生成。
5. 结果展示：实现配置表单、手动生成、Markdown 渲染和导出。
6. 企业增强：增加 SSO、审计日志、PostgreSQL、任务队列、告警与多租户隔离。

## 生产化建议

- 使用 KMS / Secret Manager 管理 Token，不在配置文件中保存明文密钥。
- 为 Web UI 增加 SSO / RBAC。
- 将报告元数据、任务执行记录写入 PostgreSQL。
- 使用 Celery / Redis 拆分采集和生成任务，提升可恢复性。
- 对 LLM 输入做脱敏和长度控制，满足企业数据合规要求。
