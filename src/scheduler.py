from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import AppConfig
from src.models import GenerateRequest
from src.services.report_service import ReportService


logger = logging.getLogger(__name__)


def create_scheduler(config: AppConfig) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    async def job() -> None:
        try:
            result = await ReportService(config).generate(GenerateRequest())
            logger.info("weekly report generated: %s", result.meta.output_path)
        except Exception:
            logger.exception("failed to generate weekly report")

    scheduler.add_job(
        job,
        # Cron 表达式只描述触发时间，时区交给服务运行环境统一管理。
        CronTrigger.from_crontab(config.schedule.cron),
        id="weekly_report_job",
        name="Generate weekly report",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    return scheduler
