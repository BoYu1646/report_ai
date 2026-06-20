# 真实飞书环境测试步骤

本文用于验证周报助手能读取真实飞书消息和日程，并按当前自然周生成周报。

## 1. 准备飞书应用

在飞书开放平台创建企业自建应用，并准备：

- `app_id`
- `app_secret`
- 需要读取的群聊 `chat_id`
- 需要读取的日历 ID，用户主日历可先使用 `primary`

建议权限：

- IM 消息只读权限，用于读取群消息。
- 日历只读权限，用于读取日程。
- 如果读取用户主日历，需要用户授权后获得 `user_access_token`。

## 2. 配置环境变量

推荐使用环境变量注入真实密钥，避免写入 `config/example.yaml`：

```bash
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"
```

如果你已有 token，也可以直接配置：

```bash
export FEISHU_TENANT_ACCESS_TOKEN="t-xxx"
export FEISHU_USER_ACCESS_TOKEN="u-xxx"
```

## 3. 单独测试飞书连通性

```bash
python scripts/test_feishu_connection.py \
  --chat-ids "oc_xxx" \
  --messages-only \
  --no-demo
```

成功时会输出：

- 飞书 API 地址。
- 当前自然周起止时间。
- 消息和日程采集数量。
- 前 15 条采集结果。

如果没有真实凭证，脚本会按配置返回演示数据；需要强制真实环境测试时加：

```bash
python scripts/test_feishu_connection.py --chat-ids "oc_xxx" --no-demo
```

如果只验证飞书消息，建议加 `--messages-only`，避免日历权限未开通时影响消息测试。

如果本机已经通过 `lark-cli auth login` 完成用户授权，也可以不传飞书密钥，直接复用本机登录态测试群消息：

```bash
python scripts/test_feishu_connection.py \
  --auth-mode lark_cli \
  --chat-ids "oc_xxx" \
  --messages-only \
  --no-demo
```

验证日程时建议先列出当前用户可访问的日历，找到目标日历的真实 `calendar_id`。飞书左侧显示名如“测试日历”不能直接填到配置里：

```bash
lark-cli calendar calendars list --as user --json
```

然后按自然周查询该日历的日程：

```bash
lark-cli calendar events instance_view \
  --as user \
  --calendar-id "primary" \
  --start-time "1781452800" \
  --end-time "1782057600" \
  --json
```

如果使用 `lark_cli` 认证模式，必须使用 `--as user` 读取个人日程；`--as bot` 通常只能看到机器人自己的空日历。若在自动化环境看到 `keychain not initialized`，请在普通终端执行 `lark-cli config keychain-downgrade`，或改用 OpenAPI 的 `user_access_token`。

## 4. 使用 Web 页面临时测试

页面支持临时输入飞书凭证，但不会把密钥保存到 YAML：

- 飞书 `App ID / App Secret / Access Token` 只进入当前后端进程内存。
- `config/example.yaml` 会继续保留 `${FEISHU_APP_ID}`、`${FEISHU_APP_SECRET}` 等占位符。
- 重启后端后，页面临时输入的密钥会失效，需要重新输入或改用环境变量。

## 5. 启动 Web 生成周报

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

打开：

```text
http://localhost:8000
```

页面操作：

1. 填写飞书 App ID / App Secret，或直接填写 Token。
2. 勾选“启用飞书消息采集”，填写飞书群聊 ID。
3. 如果本次只测消息，取消勾选“启用飞书日程采集”；如果要测日程，再填写飞书日历 ID。
4. 点击“保存配置”。此时群聊 ID、日历 ID、采集开关等普通配置会写入 YAML，密钥不会写入 YAML。
5. 点击“立即生成”。
6. 查看结果展示页中的飞书消息和日程。

## 6. 常见问题

### 401 / 403

应用凭证错误、权限未开通、用户未授权，或机器人/应用无法访问目标群聊和日历。

### 返回 0 条消息

确认群聊 ID 正确，且当前自然周内有消息。

### 返回 0 条日程

确认日历 ID 正确，并确认当前自然周内存在日程。用户主日历通常需要用户访问令牌；自建日历或共享日历需要填写对应的真实 `calendar_id`。

### 定时任务看起来没有触发

先手动点击“立即生成”。如果某个数据源采集失败，报告末尾会出现“采集告警”，页面状态也会提示告警数量。常见原因包括 Git/飞书凭证无效、`lark-cli` keychain 不可用、日历 ID 填成了显示名称，或使用 bot 身份读取用户日程。
