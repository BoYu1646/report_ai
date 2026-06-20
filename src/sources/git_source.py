from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from src.config import GitSourceConfig, is_placeholder_secret
from src.models import WorkItem


class GitSource:
    def __init__(self, config: GitSourceConfig) -> None:
        self.config = config

    async def fetch(self, week_start: datetime, week_end: datetime) -> list[WorkItem]:
        if not self.config.enabled:
            return []
        if self.config.provider != "github":
            raise ValueError("Current implementation supports github. GitLab can be added behind this adapter.")
        if not self.config.repos:
            return self._demo_items(week_start, week_end)
        if is_placeholder_secret(self.config.token) and self.config.use_demo_when_missing_token:
            return self._demo_items(week_start, week_end)

        # GitHub API 使用 UTC 时间；naive datetime 会按服务器本地时区转换，确保自然周边界不被误当成 UTC。
        since = week_start.astimezone(UTC)
        until = week_end.astimezone(UTC)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        # 公共仓库可无 Token 测试；私有仓库或更高限流需要配置 GIT_TOKEN。
        if not is_placeholder_secret(self.config.token):
            headers["Authorization"] = f"Bearer {self.config.token}"

        items: list[WorkItem] = []
        async with httpx.AsyncClient(
            base_url=self.config.api_base_url,
            headers=headers,
            timeout=30,
            trust_env=self.config.trust_env,
            follow_redirects=True,
        ) as client:
            for repo in self.config.repos:
                if self.config.include.commits:
                    items.extend(await self._fetch_commits(client, repo, since, until))
                if self.config.include.pull_requests:
                    items.extend(await self._fetch_pull_requests(client, repo, since, until))
                if self.config.include.issues:
                    items.extend(await self._fetch_issues(client, repo, since, until))
        return items

    async def _fetch_commits(
        self, client: httpx.AsyncClient, repo: str, since: datetime, until: datetime
    ) -> list[WorkItem]:
        response = await client.get(
            f"/repos/{repo}/commits",
            params={"since": since.isoformat(), "until": until.isoformat(), "per_page": 50},
        )
        self._raise_for_status(response, repo)
        items = []
        for commit in response.json():
            commit_info = commit.get("commit", {})
            author_info = commit_info.get("author") or {}
            raw_message = commit_info.get("message") or ""
            message_lines = raw_message.splitlines()
            message = message_lines[0] if message_lines else ""
            description = "\n".join(message_lines[1:]).strip() or None
            items.append(
                WorkItem(
                    source="git",
                    type="commit",
                    title=message or commit.get("sha", "")[:8],
                    description=description,
                    author=author_info.get("name"),
                    status="committed",
                    url=commit.get("html_url"),
                    updated_at=self._parse_dt(author_info.get("date")),
                    repo=repo,
                    metadata={"sha": commit.get("sha", "")[:8]},
                )
            )
        return items

    async def _fetch_pull_requests(
        self, client: httpx.AsyncClient, repo: str, since: datetime, until: datetime
    ) -> list[WorkItem]:
        response = await client.get(
            f"/repos/{repo}/pulls",
            params={"state": "all", "sort": "updated", "direction": "desc", "per_page": 50},
        )
        self._raise_for_status(response, repo)
        items = []
        for pr in response.json():
            updated_at = self._parse_dt(pr.get("updated_at"))
            if updated_at < since or updated_at >= until:
                continue
            items.append(
                WorkItem(
                    source="git",
                    type="pull_request",
                    title=pr.get("title") or f"PR #{pr.get('number')}",
                    description=pr.get("body") or None,
                    author=(pr.get("user") or {}).get("login"),
                    status="merged" if pr.get("merged_at") else pr.get("state"),
                    url=pr.get("html_url"),
                    updated_at=updated_at,
                    repo=repo,
                    metadata={"number": pr.get("number"), "draft": pr.get("draft", False)},
                )
            )
        return items

    async def _fetch_issues(
        self, client: httpx.AsyncClient, repo: str, since: datetime, until: datetime
    ) -> list[WorkItem]:
        response = await client.get(
            f"/repos/{repo}/issues",
            params={"state": "all", "since": since.isoformat(), "per_page": 50},
        )
        self._raise_for_status(response, repo)
        items = []
        for issue in response.json():
            if "pull_request" in issue:
                continue
            updated_at = self._parse_dt(issue.get("updated_at"))
            if updated_at < since or updated_at >= until:
                continue
            items.append(
                WorkItem(
                    source="git",
                    type="issue",
                    title=issue.get("title") or f"Issue #{issue.get('number')}",
                    description=issue.get("body") or None,
                    author=(issue.get("user") or {}).get("login"),
                    status=issue.get("state"),
                    url=issue.get("html_url"),
                    updated_at=updated_at,
                    repo=repo,
                    metadata={
                        "number": issue.get("number"),
                        "labels": [label.get("name") for label in issue.get("labels", [])],
                    },
                )
            )
        return items

    def _demo_items(self, week_start: datetime, week_end: datetime) -> list[WorkItem]:
        times = self._demo_times(week_start, week_end, count=3)
        repo = self.config.repos[0] if self.config.repos else "org/repo-a"
        return [
            WorkItem(
                source="git",
                type="commit",
                title="feat: 接入周报配置加载与任务调度",
                author="demo.dev",
                status="committed",
                url="https://github.com/org/repo-a/commit/demo",
                updated_at=times[0],
                repo=repo,
                metadata={"sha": "demo001"},
            ),
            WorkItem(
                source="git",
                type="pull_request",
                title="Add Markdown export endpoint",
                author="demo.dev",
                status="merged",
                url="https://github.com/org/repo-a/pull/12",
                updated_at=times[1],
                repo=repo,
                metadata={"number": 12},
            ),
            WorkItem(
                source="git",
                type="issue",
                title="Git API 凭证过期时需要明确错误提示",
                author="qa.demo",
                status="open",
                url="https://github.com/org/repo-a/issues/18",
                updated_at=times[2],
                repo=repo,
                metadata={"number": 18, "labels": ["risk", "integration"]},
            ),
        ]

    @staticmethod
    def _parse_dt(value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _raise_for_status(self, response: httpx.Response, repo: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if response.status_code == 403 and "rate limit" in response.text.lower():
                raise RuntimeError(
                    f"GitHub API 限流：仓库 `{repo}` 未配置有效 Git Token 或请求过频。"
                    "请在页面填写 Git Token，或关闭 Git 数据源后只采集飞书。"
                ) from exc
            raise

    @staticmethod
    def _demo_times(week_start: datetime, week_end: datetime, count: int) -> list[datetime]:
        start = week_start.astimezone(UTC)
        end = week_end.astimezone(UTC)
        now = datetime.now(UTC)
        anchor = min(max(now, start + timedelta(hours=1)), end - timedelta(minutes=1))
        return [max(start + timedelta(minutes=index + 1), anchor - timedelta(hours=index * 2)) for index in range(count)]
