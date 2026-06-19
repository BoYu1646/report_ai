# 真实 Git 环境测试步骤

本文用于验证周报助手能读取真实 GitHub 仓库的 commit / PR / issue，并按当前自然周生成周报。

## 1. 准备仓库信息

需要准备仓库全名：

```text
owner/repo
```

例如：

```text
microsoft/vscode
```

公共仓库可以不配置 Token 直接测试；私有仓库必须配置 Token。

## 2. 准备 GitHub Token

私有仓库或企业仓库建议使用 Token。GitHub 官方文档说明，REST API 可使用 personal access token 认证；公共资源部分接口也可以无认证访问，但限流更低。

Token 权限建议：

- Fine-grained token：选择目标仓库。
- Repository permissions：
  - Contents: Read，用于 commits。
  - Pull requests: Read，用于 PR。
  - Issues: Read，用于 issue。
  - Metadata: Read，GitHub 默认需要。

设置环境变量：

```bash
export GIT_TOKEN="你的 GitHub Token"
```

## 3. 单独测试 Git 连通性

公共仓库无 Token 测试：

```bash
python scripts/test_git_connection.py --repo microsoft/vscode
```

私有仓库测试：

```bash
export GIT_TOKEN="你的 GitHub Token"
python scripts/test_git_connection.py --repo your-org/your-private-repo
```

GitHub Enterprise 测试：

```bash
export GIT_TOKEN="你的企业 GitHub Token"
python scripts/test_git_connection.py \
  --repo your-org/your-repo \
  --api-base-url "https://github.example.com/api/v3"
```

如果本机代理不可用，可忽略代理环境变量：

```bash
python scripts/test_git_connection.py --repo microsoft/vscode --ignore-proxy
```

成功时会输出：

- Git API 地址。
- 仓库列表。
- 是否使用 Token。
- 当前自然周起止时间。
- 当前自然周内 commit / PR / issue 数量。
- 前 15 条采集结果。

## 4. 修改应用配置

编辑 `config/example.yaml`：

```yaml
sources:
  yuque:
    enabled: false

  git:
    enabled: true
    provider: github
    api_base_url: "https://api.github.com"
    token: "${GIT_TOKEN}"
    repos:
      - "your-org/your-repo"
    use_demo_when_missing_token: true
    trust_env: true
    include:
      commits: true
      pull_requests: true
      issues: true
```

如果你要在 Web 应用中强制真实公共仓库无 Token 测试，可临时改成：

```yaml
use_demo_when_missing_token: false
```

私有仓库不要关闭 Token，直接配置 `GIT_TOKEN` 即可。

## 5. 启动 Web 生成周报

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

打开：

```text
http://localhost:8000
```

页面操作：

1. 填写 Git Token。
2. 填写仓库，例如 `your-org/your-repo`。
3. 点击“保存配置”。
4. 点击“立即生成”。
5. 查看结果展示页中的 Git commit / PR / issue。
6. 点击“导出 Markdown”下载报告。

## 6. 常见问题

### 401 / 403

Token 无效、权限不足、组织未授权 fine-grained token，或触发限流。

### 404

仓库名错误，或 Token 无权访问私有仓库。GitHub 对无权限私有仓库常返回 404。

### 数据为 0

系统只统计当前自然周：周一 00:00 到下周一 00:00。确认本周是否存在提交、PR 更新或 issue 更新。

### GitHub Enterprise 失败

确认 `api_base_url` 使用 REST API 地址，例如 `https://github.example.com/api/v3`。

### ProxyError / ConnectError

当前机器无法通过代理或直连访问 GitHub。先检查 VPN/代理，或使用 `--ignore-proxy` 跳过代理环境变量。
