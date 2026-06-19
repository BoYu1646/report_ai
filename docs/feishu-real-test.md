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
  --calendar-ids "primary"
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

## 4. 启动 Web 生成周报

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

打开：

```text
http://localhost:8000
```

页面操作：

1. 填写飞书 App ID / App Secret，或直接填写 Token。
2. 填写飞书群聊 ID。
3. 填写飞书日历 ID。
4. 点击“保存配置”。
5. 点击“立即生成”。
6. 查看结果展示页中的飞书消息和日程。

## 5. 常见问题

### 401 / 403

应用凭证错误、权限未开通、用户未授权，或机器人/应用无法访问目标群聊和日历。

### 返回 0 条消息

确认群聊 ID 正确，且当前自然周内有消息。

### 返回 0 条日程

确认日历 ID 正确，并确认当前自然周内存在日程。用户主日历通常需要用户访问令牌。
