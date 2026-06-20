from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from src.agent.weekly_report_agent import WeeklyReportAgent
from src.config import AppConfig, ROOT_DIR
from src.models import GenerateRequest, ReportMeta, ReportResponse, WorkItem
from src.sources.feishu_source import FeishuSource, PartialFetchError
from src.sources.git_source import GitSource
from src.time_window import current_natural_week


class ReportService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    async def generate(self, request: GenerateRequest | None = None) -> ReportResponse:
        request = request or GenerateRequest()
        # 周报固定按当前自然周生成，避免“最近 7 天”导致跨周数据混入。
        week_start, week_end = current_natural_week()
        items, collection_errors = await self._collect_items(week_start, week_end)
        markdown, used_llm = await WeeklyReportAgent(self.config).generate(items, week_start, week_end, request.template)
        if collection_errors:
            markdown = f"{markdown.rstrip()}\n\n{self._format_collection_errors(collection_errors)}\n"
        output_path = self._write_report(markdown)
        meta = ReportMeta(
            generated_at=datetime.now(),
            week_start=week_start,
            week_end=week_end,
            output_path=str(output_path),
            item_count=len(items),
            source_counts=dict(Counter(item.source for item in items)),
            used_llm=used_llm,
            collection_errors=collection_errors,
        )
        return ReportResponse(markdown=markdown, meta=meta)

    def latest_report_path(self) -> Path | None:
        output_dir = self._output_dir()
        reports = sorted(output_dir.glob(f"{self.config.report.filename_prefix}-*.md"))
        return reports[-1] if reports else None

    def latest_markdown(self) -> str:
        latest = self.latest_report_path()
        if not latest:
            return "# 暂无周报\n\n点击“立即生成”创建第一份周报。\n"
        return latest.read_text(encoding="utf-8")

    async def _collect_items(self, week_start: datetime, week_end: datetime) -> tuple[list[WorkItem], list[str]]:
        items: list[WorkItem] = []
        errors: list[str] = []

        for name, source in (
            ("Git", GitSource(self.config.sources.git)),
            ("飞书", FeishuSource(self.config.sources.feishu)),
        ):
            try:
                items.extend(await source.fetch(week_start, week_end))
            except PartialFetchError as exc:
                items.extend(exc.items)
                errors.extend(f"{name} 数据源部分采集失败：{error}" for error in exc.errors)
            except Exception as exc:
                errors.append(f"{name} 数据源采集失败：{exc}")

        return sorted(items, key=self._sort_timestamp, reverse=True), errors

    @staticmethod
    def _format_collection_errors(errors: list[str]) -> str:
        details = "\n".join(f"- {error}" for error in errors)
        return f"## 采集告警\n{details}"

    @staticmethod
    def _sort_timestamp(item: WorkItem) -> float:
        # 数据源可能混用带时区和不带时区的 datetime；统一转成时间戳后再排序。
        return item.updated_at.timestamp()

    def _write_report(self, markdown: str) -> Path:
        output_dir = self._output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self.config.report.filename_prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        output_path = output_dir / filename
        output_path.write_text(markdown, encoding="utf-8")
        return output_path

    def _output_dir(self) -> Path:
        configured = Path(self.config.report.output_dir)
        return configured if configured.is_absolute() else ROOT_DIR / configured
