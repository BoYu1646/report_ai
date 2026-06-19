from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from src.config import YuqueSourceConfig, is_placeholder_secret
from src.models import WorkItem


class YuqueSource:
    def __init__(self, config: YuqueSourceConfig) -> None:
        self.config = config

    async def fetch(self, week_start: datetime, week_end: datetime) -> list[WorkItem]:
        if not self.config.enabled or not self.config.include_docs:
            return []
        if is_placeholder_secret(self.config.token) or not self.config.namespace:
            return self._demo_items(week_start, week_end)

        # 语雀接口返回时间通常带时区；查询窗口统一转为 UTC 后再比较。
        since = week_start.astimezone(UTC)
        until = week_end.astimezone(UTC)
        headers = {
            "X-Auth-Token": self.config.token or "",
            # 真实语雀环境建议显式传 User-Agent，便于平台识别调用方。
            "User-Agent": self.config.user_agent,
        }
        async with httpx.AsyncClient(
            base_url=self.config.api_base_url,
            headers=headers,
            timeout=30,
            follow_redirects=True,
        ) as client:
            response = await client.get(f"/repos/{self.config.namespace}/docs")
            response.raise_for_status()
            docs = response.json().get("data", [])

        items: list[WorkItem] = []
        for doc in docs:
            updated_at = self._parse_dt(doc.get("updated_at"))
            if updated_at < since or updated_at >= until:
                continue
            items.append(
                WorkItem(
                    source="yuque",
                    type="doc",
                    title=doc.get("title") or doc.get("slug") or "未命名文档",
                    author=str(doc.get("user_id") or ""),
                    status="updated",
                    url=doc.get("url") or doc.get("html_url"),
                    updated_at=updated_at,
                    metadata={"slug": doc.get("slug"), "namespace": self.config.namespace},
                )
            )
        return items

    def _demo_items(self, week_start: datetime, week_end: datetime) -> list[WorkItem]:
        times = self._demo_times(week_start, week_end, count=2)
        return [
            WorkItem(
                source="yuque",
                type="doc",
                title="周报助手 Agent 设计方案",
                author="doc.owner",
                status="updated",
                url="https://www.yuque.com/team/project/demo",
                updated_at=times[0],
                metadata={"namespace": self.config.namespace or "team/project"},
            ),
            WorkItem(
                source="yuque",
                type="doc",
                title="Git 与语雀数据源字段映射说明",
                author="doc.owner",
                status="updated",
                url="https://www.yuque.com/team/project/mapping",
                updated_at=times[1],
                metadata={"namespace": self.config.namespace or "team/project"},
            ),
        ]

    @staticmethod
    def _parse_dt(value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _demo_times(week_start: datetime, week_end: datetime, count: int) -> list[datetime]:
        start = week_start.astimezone(UTC)
        end = week_end.astimezone(UTC)
        now = datetime.now(UTC)
        anchor = min(max(now, start + timedelta(hours=1)), end - timedelta(minutes=1))
        return [max(start + timedelta(minutes=index + 1), anchor - timedelta(hours=index * 3)) for index in range(count)]
