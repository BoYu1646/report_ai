from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from typing import Any

import httpx

from src.config import FeishuSourceConfig, is_placeholder_secret
from src.models import WorkItem


class FeishuSource:
    def __init__(self, config: FeishuSourceConfig) -> None:
        self.config = config

    async def fetch(self, week_start: datetime, week_end: datetime) -> list[WorkItem]:
        if not self.config.enabled:
            return []
        if self._missing_credentials():
            if self.config.use_demo_when_missing_credentials:
                return self._demo_items(week_start, week_end)
            raise RuntimeError("飞书数据源缺少凭证：请配置 app_id/app_secret、tenant_access_token 或 user_access_token。")

        token = await self._access_token()
        items: list[WorkItem] = []
        async with httpx.AsyncClient(
            base_url=self.config.api_base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
            follow_redirects=True,
        ) as client:
            if self.config.messages.enabled:
                items.extend(await self._fetch_messages(client, week_start, week_end))
            if self.config.calendar.enabled:
                items.extend(await self._fetch_calendar_events(client, week_start, week_end))
        return items

    def _missing_credentials(self) -> bool:
        has_token = not is_placeholder_secret(self.config.tenant_access_token) or not is_placeholder_secret(
            self.config.user_access_token
        )
        has_app = not is_placeholder_secret(self.config.app_id) and not is_placeholder_secret(self.config.app_secret)
        return not (has_token or has_app)

    async def _access_token(self) -> str:
        if not is_placeholder_secret(self.config.user_access_token):
            return self.config.user_access_token or ""
        if not is_placeholder_secret(self.config.tenant_access_token):
            return self.config.tenant_access_token or ""

        async with httpx.AsyncClient(base_url=self.config.api_base_url, timeout=30, follow_redirects=True) as client:
            response = await client.post(
                "/auth/v3/tenant_access_token/internal",
                json={"app_id": self.config.app_id, "app_secret": self.config.app_secret},
            )
            response.raise_for_status()
            data = self._data(response.json(), "tenant_access_token")
        token = data.get("tenant_access_token")
        if not token:
            raise RuntimeError("飞书认证失败：响应中缺少 tenant_access_token。")
        return str(token)

    async def _fetch_messages(
        self, client: httpx.AsyncClient, week_start: datetime, week_end: datetime
    ) -> list[WorkItem]:
        if not self.config.messages.chat_ids:
            return []
        items: list[WorkItem] = []
        start_time = int(week_start.timestamp())
        end_time = int(week_end.timestamp())
        for chat_id in self.config.messages.chat_ids:
            response = await client.get(
                "/im/v1/messages",
                params={
                    "container_id_type": "chat",
                    "container_id": chat_id,
                    "start_time": start_time,
                    "end_time": end_time,
                    "sort_type": "ByCreateTimeAsc",
                    "page_size": self.config.messages.limit_per_chat,
                },
            )
            response.raise_for_status()
            data = self._data(response.json(), "messages")
            for message in data.get("items", []):
                title = self._message_title(message)
                if self._filtered_by_keywords(title):
                    continue
                items.append(
                    WorkItem(
                        source="feishu",
                        type="message",
                        title=title,
                        author=self._sender_name(message),
                        status="sent",
                        url=None,
                        updated_at=self._parse_ts(message.get("update_time") or message.get("create_time")),
                        metadata={
                            "chat_id": chat_id,
                            "message_id": message.get("message_id"),
                            "message_type": message.get("msg_type"),
                        },
                    )
                )
        return items

    async def _fetch_calendar_events(
        self, client: httpx.AsyncClient, week_start: datetime, week_end: datetime
    ) -> list[WorkItem]:
        items: list[WorkItem] = []
        for calendar_id in self.config.calendar.calendar_ids:
            response = await client.get(
                f"/calendar/v4/calendars/{calendar_id}/events",
                params={
                    "start_time": int(week_start.timestamp()),
                    "end_time": int(week_end.timestamp()),
                    "page_size": self.config.calendar.limit_per_calendar,
                },
            )
            response.raise_for_status()
            data = self._data(response.json(), "calendar_events")
            for event in data.get("items", []):
                start_at = self._parse_event_time(event.get("start_time")) or week_start
                if start_at < week_start or start_at >= week_end:
                    continue
                items.append(
                    WorkItem(
                        source="feishu",
                        type="calendar_event",
                        title=event.get("summary") or "未命名日程",
                        author=(event.get("organizer") or {}).get("display_name"),
                        status=event.get("status") or "scheduled",
                        url=event.get("app_link"),
                        updated_at=start_at,
                        metadata={
                            "calendar_id": calendar_id,
                            "event_id": event.get("event_id"),
                            "description": event.get("description"),
                        },
                    )
                )
        return items

    def _filtered_by_keywords(self, title: str) -> bool:
        keywords = [keyword for keyword in self.config.messages.keywords if keyword]
        return bool(keywords) and not any(keyword in title for keyword in keywords)

    @staticmethod
    def _data(payload: dict[str, Any], scope: str) -> dict[str, Any]:
        code = payload.get("code", 0)
        if code not in (0, None):
            raise RuntimeError(f"飞书 {scope} API 请求失败：code={code}, msg={payload.get('msg')}")
        return payload.get("data") or {}

    @staticmethod
    def _message_title(message: dict[str, Any]) -> str:
        content = message.get("body", {}).get("content") or message.get("content") or ""
        if not content:
            return "空消息"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return str(content)[:160]
        if isinstance(parsed, dict):
            text = parsed.get("text")
            if isinstance(text, str):
                return text[:160]
            title = parsed.get("title")
            if isinstance(title, str):
                return title[:160]
        return str(parsed)[:160]

    @staticmethod
    def _sender_name(message: dict[str, Any]) -> str | None:
        sender = message.get("sender") or {}
        return (
            sender.get("sender_id", {}).get("open_id")
            or sender.get("id")
            or sender.get("name")
            or message.get("sender_id")
        )

    @staticmethod
    def _parse_ts(value: Any) -> datetime:
        if value is None:
            return datetime.now(UTC)
        text = str(value)
        if text.isdigit():
            number: int | float = int(text)
            if number > 10_000_000_000:
                number = number / 1000
            return datetime.fromtimestamp(number, UTC)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))

    def _parse_event_time(self, value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, dict):
            if value.get("timestamp"):
                return self._parse_ts(value["timestamp"])
            if value.get("date"):
                return datetime.combine(datetime.fromisoformat(value["date"]).date(), time.min)
        return self._parse_ts(value)

    def _demo_items(self, week_start: datetime, week_end: datetime) -> list[WorkItem]:
        times = self._demo_times(week_start, week_end, count=3)
        return [
            WorkItem(
                source="feishu",
                type="message",
                title="完成周报助手飞书消息源字段映射讨论",
                author="demo.user",
                status="sent",
                updated_at=times[0],
                metadata={"chat_id": "oc_demo", "message_id": "om_demo_1"},
            ),
            WorkItem(
                source="feishu",
                type="calendar_event",
                title="研发周会：确认本周交付进度与风险",
                author="demo.organizer",
                status="scheduled",
                updated_at=times[1],
                metadata={"calendar_id": "primary", "event_id": "event_demo_1"},
            ),
            WorkItem(
                source="feishu",
                type="message",
                title="风险提醒：飞书应用权限需要在上线前完成审批",
                author="demo.pm",
                status="sent",
                updated_at=times[2],
                metadata={"chat_id": "oc_demo", "message_id": "om_demo_2"},
            ),
        ]

    @staticmethod
    def _demo_times(week_start: datetime, week_end: datetime, count: int) -> list[datetime]:
        start = week_start.astimezone(UTC)
        end = week_end.astimezone(UTC)
        now = datetime.now(UTC)
        anchor = min(max(now, start + timedelta(hours=1)), end - timedelta(minutes=1))
        return [max(start + timedelta(minutes=index + 1), anchor - timedelta(hours=index * 4)) for index in range(count)]
