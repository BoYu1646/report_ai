from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "example.yaml"
DEFAULT_REPORT_TEMPLATE = (
    "# {title}\n\n"
    "> 周期：{week_start} 至 {week_end}\n"
    "> 数据概览：Git {git_count} 条，语雀 {yuque_count} 条。\n\n"
    "## 本周完成\n{done}\n\n"
    "## 进行中\n{in_progress}\n\n"
    "## 风险/阻塞\n{risks}\n\n"
    "## 下周计划\n{next_week}\n\n"
    "## 数据来源\n{sources}\n"
)


class ScheduleConfig(BaseModel):
    cron: str = "* * * * *"


class GitIncludeConfig(BaseModel):
    commits: bool = True
    pull_requests: bool = True
    issues: bool = True


class GitSourceConfig(BaseModel):
    enabled: bool = True
    provider: Literal["github", "gitlab"] = "github"
    api_base_url: str = "https://api.github.com"
    token: str | None = None
    repos: list[str] = Field(default_factory=list)
    include: GitIncludeConfig = Field(default_factory=GitIncludeConfig)
    use_demo_when_missing_token: bool = True
    trust_env: bool = True


class YuqueSourceConfig(BaseModel):
    enabled: bool = True
    api_base_url: str = "https://www.yuque.com/api/v2"
    token: str | None = None
    namespace: str | None = None
    user_agent: str = "report-ai-weekly-assistant"
    include_docs: bool = True


class SourcesConfig(BaseModel):
    git: GitSourceConfig = Field(default_factory=GitSourceConfig)
    yuque: YuqueSourceConfig = Field(default_factory=YuqueSourceConfig)


class LLMConfig(BaseModel):
    provider: Literal["openai_compatible"] = "openai_compatible"
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    base_url: str | None = "https://api.openai.com/v1"
    temperature: float = Field(default=0.2, ge=0, le=2)
    timeout_seconds: int = Field(default=60, ge=5, le=300)


class ReportConfig(BaseModel):
    template: str = DEFAULT_REPORT_TEMPLATE
    title: str = "研发工作周报"
    sections: list[str] = Field(default_factory=lambda: ["done", "in_progress", "risks", "next_week"])
    output_dir: str = "./reports"
    filename_prefix: str = "weekly-report"
    language: str = "zh-CN"

    @field_validator("sections")
    @classmethod
    def validate_sections(cls, value: list[str]) -> list[str]:
        required = {"done", "in_progress", "risks", "next_week"}
        missing = required.difference(value)
        if missing:
            raise ValueError(f"report.sections missing required sections: {sorted(missing)}")
        return value

    @field_validator("template")
    @classmethod
    def validate_template(cls, value: str) -> str:
        return value if value.strip() else DEFAULT_REPORT_TEMPLATE


class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    enable_export: bool = True


class AppConfig(BaseModel):
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    web: WebConfig = Field(default_factory=WebConfig)


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


def is_placeholder_secret(value: str | None) -> bool:
    return not value or value.startswith("${") or value.endswith("}")


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(_expand_env(data))


def save_config(config: AppConfig, path: Path | str = DEFAULT_CONFIG_PATH) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
