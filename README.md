# 自动生成工作周报助手

企业级研发周报 Agent：按配置定时采集 Git commit / PR / issue 与飞书消息、日程，通过 LangChain 1.x 调用大模型生成结构化 Markdown 周报，并提供 FastAPI + Web UI 的结果展示、配置和导出能力。

> 说明：题目名称提到“每 2 分钟”，必选实现项提到“每分钟定时触发”。本项目采用可配置 Cron，示例配置默认每分钟触发；如需每 2 分钟触发，将 `schedule.cron` 改为 `*/2 * * * *`。

## 项目能力

- 可配置：通过 `config/example.yaml` 修改调度、Git、飞书、LLM、模板、输出目录等行为。
- 自动触发：APScheduler 按 Cron 定时生成，示例默认每分钟。
- 自然周：所有周报固定采集当前自然周，即周一 00:00 到下周一 00:00，不使用“当前时间往前 7 天”。
- 数据源：接入 GitHub commit / PR / issue，以及飞书消息 / 日程。
- Agent 汇总：LangChain 1.x + ChatOpenAI 兼容接口，输出 `本周完成`、`进行中`、`风险/阻塞`、`下周计划`。
- 结果展示：Web UI 渲染 Markdown，支持手动触发与导出 `.md` 文件。
- 可直接运行：未配置真实 Git / 飞书凭证时可使用演示数据；未配置模型 Key 时使用本地兜底生成器。

## 技术栈

后端：

- Python 3.11+
- FastAPI：API 服务与静态页面托管
- APScheduler：Cron 定时任务
- LangChain 1.x：Prompt、LLM 调用与输出编排
- langchain-openai 1.x：OpenAI / OpenAI-compatible 模型接入
- Pydantic 2.x：配置与接口模型校验
- httpx：GitHub API 与飞书 OpenAPI 调用
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
│   ├── design.md
│   ├── git-real-test.md
│   └── feishu-real-test.md
├── reports/
├── scripts/
│   ├── test_git_connection.py
│   └── test_feishu_connection.py
├── src/
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── scheduler.py
│   ├── agent/
│   │   └── weekly_report_agent.py
│   ├── services/
│   │   └── report_service.py
│   └── sources/
│       ├── git_source.py
│       └── feishu_source.py
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
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"
export OPENAI_API_KEY="sk_xxx"
```

关键字段：

| 字段 | 说明 |
| --- | --- |
| `schedule.cron` | Cron 表达式，示例默认 `* * * * *` 每分钟执行 |
| `sources.git.repos` | GitHub 仓库列表，例如 `org/repo-a` |
| `sources.git.token` | Git API Token |
| `sources.git.use_demo_when_missing_token` | 缺少 Token 时是否使用演示 Git 数据 |
| `sources.feishu.enabled` | 是否启用飞书数据源 |
| `sources.feishu.app_id/app_secret` | 飞书应用凭证，系统会自动换取 `tenant_access_token` |
| `sources.feishu.tenant_access_token` | 可直接传入租户访问令牌 |
| `sources.feishu.user_access_token` | 读取用户主日历等个人资源时可配置用户访问令牌 |
| `sources.feishu.messages.chat_ids` | 飞书群聊 ID 列表，例如 `oc_xxx` |
| `sources.feishu.calendar.calendar_ids` | 飞书日历 ID 列表，默认 `primary` |
| `report.template` | 自定义 Markdown 模板，支持 `{git_count}`、`{feishu_count}`、`{done}` 等占位符 |
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

## 真实数据源测试

GitHub：

```bash
python scripts/test_git_connection.py --repo microsoft/vscode
```

飞书：

```bash
python scripts/test_feishu_connection.py --chat-ids "oc_xxx" --calendar-ids "primary"
```

详细说明见：

- `docs/git-real-test.md`
- `docs/feishu-real-test.md`

## AI 使用说明

Agent 输入为统一 `WorkItem`：

- Git commit：标题、作者、提交时间、仓库、commit URL。
- PR：标题、作者、状态、更新时间、PR URL。
- Issue：标题、作者、状态、标签、Issue URL。
- 飞书消息：消息摘要、发送人、群聊、发送时间。
- 飞书日程：日程标题、组织者、日程时间、日历 ID。

Agent 流程：

1. `ReportService` 按服务器本地日期计算当前自然周窗口：周一 00:00 到下周一 00:00。
2. `GitSource` 采集当前自然周内的 commit / PR / issue。
3. `FeishuSource` 采集当前自然周内的飞书消息 / 日程。
4. 数据源适配器将外部 API 响应归一化为 `WorkItem`。
5. `WeeklyReportAgent` 使用 LangChain 1.x 组装 Prompt、自定义模板和自然周边界后调用模型。
6. 模型不可用时使用本地兜底生成器，保证系统可演示、可验收。
7. Markdown 保存到 `reports/weekly-report-*.md`。
8. Web UI 调用 `/api/reports/latest` 渲染，调用 `/api/reports/export` 导出。

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
3. Git 接入：实现 commit / PR / issue 采集。
4. 飞书接入：实现消息 / 日程采集和凭证换取。
5. Agent 生成：实现 LangChain Prompt、模型调用、章节兜底校验和本地兜底生成。
6. 结果展示：实现配置表单、手动生成、Markdown 渲染和导出。
7. 企业增强：增加 SSO、审计日志、PostgreSQL、任务队列、告警与多租户隔离。

## 生产化建议

- 使用 KMS / Secret Manager 管理 Token，不在配置文件中保存明文密钥。
- 为 Web UI 增加 SSO / RBAC。
- 将报告元数据、任务执行记录写入 PostgreSQL。
- 使用 Celery / Redis 拆分采集和生成任务，提升可恢复性。
- 对 LLM 输入做脱敏和长度控制，满足企业数据合规要求。
