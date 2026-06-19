from __future__ import annotations

from datetime import datetime, time, timedelta


def current_natural_week(now: datetime | None = None) -> tuple[datetime, datetime]:
    """按服务器本地日期计算自然周：周一 00:00 到下周一 00:00。"""
    current = now or datetime.now()
    week_start_date = current.date() - timedelta(days=current.weekday())
    week_start = datetime.combine(week_start_date, time.min)
    week_end = week_start + timedelta(days=7)
    return week_start, week_end
