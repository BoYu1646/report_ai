from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.config import DEFAULT_CONFIG_PATH, is_placeholder_secret, load_config
from src.sources.yuque_source import YuqueSource
from src.time_window import current_natural_week


async def main() -> None:
    parser = argparse.ArgumentParser(description="测试真实语雀环境连通性和当前自然周文档更新。")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="配置文件路径，默认 config/example.yaml")
    parser.add_argument("--namespace", help="语雀知识库 namespace，例如 team/project；不传则读取配置文件")
    parser.add_argument("--api-base-url", help="语雀 API 地址；企业语雀可传 https://your-company.yuque.com/api/v2")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    yuque = config.sources.yuque
    if args.namespace:
        yuque.namespace = args.namespace
    if args.api_base_url:
        yuque.api_base_url = args.api_base_url

    if is_placeholder_secret(yuque.token):
        raise SystemExit("缺少真实 YUQUE_TOKEN。请先执行：export YUQUE_TOKEN='你的语雀 Token'")
    if not yuque.namespace:
        raise SystemExit("缺少 sources.yuque.namespace，例如 team/project")

    week_start, week_end = current_natural_week()
    print(f"语雀 API: {yuque.api_base_url}")
    print(f"知识库: {yuque.namespace}")
    print(f"自然周: {week_start} 至 {week_end}")

    items = await YuqueSource(yuque).fetch(week_start, week_end)
    print(f"当前自然周文档更新数量: {len(items)}")
    for item in items[:10]:
        print(f"- {item.updated_at.isoformat()} {item.title} {item.url or ''}")


if __name__ == "__main__":
    asyncio.run(main())
