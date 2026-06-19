from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkItem(BaseModel):
    source: Literal["git", "yuque"]
    type: str
    title: str
    author: str | None = None
    status: str | None = None
    url: str | None = None
    updated_at: datetime
    repo: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    template: str | None = None


class ReportMeta(BaseModel):
    generated_at: datetime
    week_start: datetime
    week_end: datetime
    output_path: str
    item_count: int
    source_counts: dict[str, int]
    used_llm: bool


class ReportResponse(BaseModel):
    markdown: str
    meta: ReportMeta
