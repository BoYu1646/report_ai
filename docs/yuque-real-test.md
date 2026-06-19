# 真实语雀环境测试步骤

本文用于在真实语雀环境中验证周报助手能读取语雀文档更新，并按当前自然周生成周报。

## 1. 准备语雀信息

需要准备三项信息：

1. 语雀 API Token。
2. 知识库 namespace。
3. API Base URL。

Token 获取路径：

- 登录语雀。
- 进入个人设置 / Token 页面。
- 创建 Token，并勾选读取知识库和文档所需权限。

namespace 获取方式：

- 如果知识库地址是 `https://www.yuque.com/team/project`，则 namespace 是 `team/project`。
- 如果是企业语雀域名，namespace 仍取路径部分，例如 `https://your-company.yuque.com/team/project` 对应 `team/project`。

API Base URL：

- 普通语雀：`https://www.yuque.com/api/v2`
- 企业语雀：`https://your-company.yuque.com/api/v2`

## 2. 配置环境变量

不要把真实 Token 写入仓库。推荐使用环境变量：

```bash
export YUQUE_TOKEN="你的语雀 Token"
```

如需同时测试 LLM：

```bash
export OPENAI_API_KEY="你的模型 Key"
```

## 3. 修改配置文件

编辑 `config/example.yaml` 中的语雀配置：

```yaml
sources:
  yuque:
    enabled: true
    api_base_url: "https://www.yuque.com/api/v2"
    token: "${YUQUE_TOKEN}"
    namespace: "team/project"
    user_agent: "report-ai-weekly-assistant"
    include_docs: true
```

企业语雀把 `api_base_url` 改为企业域名，例如：

```yaml
api_base_url: "https://your-company.yuque.com/api/v2"
```

## 4. 先单独测试语雀连通性

运行：

```bash
python scripts/test_yuque_connection.py
```

也可以不改配置文件，直接传知识库和企业域名：

```bash
python scripts/test_yuque_connection.py \
  --namespace "team/project" \
  --api-base-url "https://www.yuque.com/api/v2"
```

企业语雀示例：

```bash
python scripts/test_yuque_connection.py \
  --namespace "team/project" \
  --api-base-url "https://your-company.yuque.com/api/v2"
```

成功时会输出：

- 当前语雀 API 地址。
- 知识库 namespace。
- 当前自然周起止时间。
- 当前自然周内更新的文档数量。
- 前 10 条文档标题与链接。

如果数量为 0，先确认当前自然周内是否真的有文档更新。可以在语雀里随便更新一个测试文档标题或正文，再重新运行脚本。

## 5. 启动 Web 服务测试

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

打开：

```text
http://localhost:8000
```

页面操作：

1. 确认语雀 Token、namespace、API 地址配置正确。
2. 点击“立即生成”。
3. 查看“结果展示”区域是否出现语雀文档更新。
4. 点击“导出 Markdown”下载报告。

## 6. 常见问题

### 401 / 403

Token 无效、权限不足或账号没有对应知识库访问权限。重新创建 Token，并确认勾选只读权限。

### 404

通常是 `namespace` 错误，或普通/企业语雀域名配置错了。

### 返回 0 条文档

系统只统计当前自然周：周一 00:00 到下周一 00:00。请确认本自然周内有语雀文档更新。

### 企业语雀无法访问

把 `api_base_url` 改为企业空间域名的 `/api/v2`，例如 `https://your-company.yuque.com/api/v2`。
