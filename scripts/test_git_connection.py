from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.config import DEFAULT_CONFIG_PATH, load_config
from src.sources.git_source import GitSource
from src.time_window import current_natural_week


async def main() -> None:
    parser = argparse.ArgumentParser(description="测试真实 GitHub 环境的 commit / PR / issue 采集。")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="配置文件路径，默认 config/example.yaml")
    parser.add_argument("--repo", action="append", help="仓库全名，例如 microsoft/vscode；可重复传多个")
    parser.add_argument("--api-base-url", help="GitHub API 地址，GitHub Enterprise 可传 https://host/api/v3")
    parser.add_argument("--token-env", default="GIT_TOKEN", help="Token 环境变量名，默认 GIT_TOKEN")
    parser.add_argument("--ignore-proxy", action="store_true", help="忽略 HTTP_PROXY/HTTPS_PROXY 等代理环境变量")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    git = config.sources.git
    if args.repo:
        git.repos = args.repo
    if args.api_base_url:
        git.api_base_url = args.api_base_url
    git.token = os.getenv(args.token_env) or git.token
    # 连通性测试必须访问真实 API；公共仓库允许无 Token，私有仓库需要 Token。
    git.use_demo_when_missing_token = False
    if args.ignore_proxy:
        git.trust_env = False

    if not git.repos:
        raise SystemExit("缺少仓库。请传 --repo owner/name，或在配置中填写 sources.git.repos。")

    week_start, week_end = current_natural_week()
    print(f"Git API: {git.api_base_url}")
    print(f"仓库: {', '.join(git.repos)}")
    print(f"认证: {'使用 Token' if git.token and not git.token.startswith('${') else '无 Token，仅适用于公共仓库'}")
    print(f"自然周: {week_start} 至 {week_end}")

    try:
        items = await GitSource(git).fetch(week_start, week_end)
    except httpx.HTTPStatusError as exc:
        response = exc.response
        print(f"Git API 请求失败: HTTP {response.status_code}")
        print(response.text[:1000])
        raise SystemExit(1) from exc
    except httpx.RequestError as exc:
        print(f"Git API 网络请求失败: {exc.__class__.__name__}")
        print("请检查本机网络、代理、VPN、防火墙，或尝试加上 --ignore-proxy。")
        raise SystemExit(1) from exc

    counts = Counter(item.type for item in items)
    print(f"当前自然周采集数量: {len(items)}")
    print(f"- commits: {counts.get('commit', 0)}")
    print(f"- pull_requests: {counts.get('pull_request', 0)}")
    print(f"- issues: {counts.get('issue', 0)}")
    for item in items[:15]:
        print(f"- [{item.type}] {item.updated_at.isoformat()} {item.title} {item.url or ''}")


if __name__ == "__main__":
    asyncio.run(main())
