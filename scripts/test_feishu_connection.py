from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.config import DEFAULT_CONFIG_PATH, load_config
from src.sources.feishu_source import FeishuSource
from src.time_window import current_natural_week


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


async def main() -> None:
    parser = argparse.ArgumentParser(description="测试真实飞书消息/日程采集。")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="配置文件路径，默认 config/example.yaml")
    parser.add_argument("--chat-ids", help="飞书群聊 chat_id，逗号分隔，例如 oc_xxx,oc_yyy")
    parser.add_argument("--calendar-ids", help="飞书日历 ID，逗号分隔，默认读取配置")
    parser.add_argument("--messages-only", action="store_true", help="只测试飞书消息，关闭日程采集")
    parser.add_argument("--calendar-only", action="store_true", help="只测试飞书日程，关闭消息采集")
    parser.add_argument("--no-demo", action="store_true", help="缺少飞书凭证时不使用演示数据")
    args = parser.parse_args()
    if args.messages_only and args.calendar_only:
        raise SystemExit("--messages-only 与 --calendar-only 不能同时使用。")

    config = load_config(Path(args.config))
    feishu = config.sources.feishu
    if args.chat_ids:
        feishu.messages.chat_ids = _csv(args.chat_ids)
    if args.calendar_ids:
        feishu.calendar.calendar_ids = _csv(args.calendar_ids)
    if args.no_demo:
        feishu.use_demo_when_missing_credentials = False
    if args.messages_only:
        feishu.messages.enabled = True
        feishu.calendar.enabled = False
    if args.calendar_only:
        feishu.messages.enabled = False
        feishu.calendar.enabled = True

    week_start, week_end = current_natural_week()
    print(f"飞书 API: {feishu.api_base_url}")
    print(f"自然周: {week_start} 至 {week_end}")
    print(f"消息采集: {'启用' if feishu.messages.enabled else '关闭'}，chat_ids: {feishu.messages.chat_ids or '未配置'}")
    print(f"日程采集: {'启用' if feishu.calendar.enabled else '关闭'}，calendar_ids: {feishu.calendar.calendar_ids or '未配置'}")

    try:
        items = await FeishuSource(feishu).fetch(week_start, week_end)
    except httpx.HTTPStatusError as exc:
        response = exc.response
        print(f"飞书 API 请求失败: HTTP {response.status_code}")
        print(response.text[:1000])
        raise SystemExit(1) from exc
    except httpx.RequestError as exc:
        print(f"飞书 API 网络请求失败: {exc.__class__.__name__}")
        print("请检查本机网络、代理、VPN、防火墙。")
        raise SystemExit(1) from exc
    except RuntimeError as exc:
        print(str(exc))
        raise SystemExit(1) from exc

    counts = Counter(item.type for item in items)
    print(f"当前自然周飞书采集数量: {len(items)}")
    print(f"- messages: {counts.get('message', 0)}")
    print(f"- calendar_events: {counts.get('calendar_event', 0)}")
    for item in items[:15]:
        print(f"- [{item.type}] {item.updated_at.isoformat()} {item.title}")


if __name__ == "__main__":
    asyncio.run(main())
