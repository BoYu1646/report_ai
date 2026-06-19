from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from src.agent.weekly_report_agent import WeeklyReportAgent
from src.config import AppConfig, ROOT_DIR
from src.models import GenerateRequest, ReportMeta, ReportResponse, WorkItem
from src.sources.git_source import GitSource
from src.sources.yuque_source import YuqueSource
from src.time_window import current_natural_week


class ReportService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    async def generate(self, request: GenerateRequest | None = None) -> ReportResponse:
        request = request or GenerateRequest()
        # 周报固定按当前自然周生成，避免“最近 7 天”导致跨周数据混入。
        week_start, week_end = current_natural_week()
        items = await self._collect_items(week_start, week_end)
        markdown, used_llm = await WeeklyReportAgent(self.config).generate(items, week_start, week_end, request.template)
        output_path = self._write_report(markdown)
        meta = ReportMeta(
            generated_at=datetime.now(),
            week_start=week_start,
            week_end=week_end,
            output_path=str(output_path),
            item_count=len(items),
            source_counts=dict(Counter(item.source for item in items)),
            used_llm=used_llm,
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

    async def _collect_items(self, week_start: datetime, week_end: datetime) -> list[WorkItem]:
        git_items = await GitSource(self.config.sources.git).fetch(week_start, week_end)
        yuque_items = await YuqueSource(self.config.sources.yuque).fetch(week_start, week_end)
        return sorted([*git_items, *yuque_items], key=lambda item: item.updated_at, reverse=True)

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
