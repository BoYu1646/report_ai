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
    "> 数据概览：Git {git_count} 条，飞书 {feishu_count} 条。\n\n"
    "## 本周完成\n{done}\n\n"
    "## 进行中\n{in_progress}\n\n"
    "## 风险/阻塞\n{risks}\n\n"
    "## 下周计划\n{next_week}\n\n"
    "## 数据来源\n{sources}\n"
)

SECRET_FIELD_PATHS: tuple[tuple[str, ...], ...] = (
    ("sources", "git", "token"),
    ("sources", "feishu", "app_id"),
    ("sources", "feishu", "app_secret"),
    ("sources", "feishu", "tenant_access_token"),
    ("sources", "feishu", "user_access_token"),
    ("llm", "api_key"),
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


class FeishuMessageConfig(BaseModel):
    enabled: bool = True
    chat_ids: list[str] = Field(default_factory=list)
    limit_per_chat: int = Field(default=50, ge=1, le=200)

    @field_validator("chat_ids", mode="before")
    @classmethod
    def coerce_none_to_list(cls, value: object) -> object:
        return [] if value is None else value


class FeishuCalendarConfig(BaseModel):
    enabled: bool = True
    calendar_ids: list[str] = Field(default_factory=lambda: ["primary"])
    limit_per_calendar: int = Field(default=50, ge=1, le=200)

    @field_validator("calendar_ids", mode="before")
    @classmethod
    def coerce_none_to_list(cls, value: object) -> object:
        return ["primary"] if value is None else value


class FeishuSourceConfig(BaseModel):
    enabled: bool = True
    api_base_url: str = "https://open.feishu.cn/open-apis"
    app_id: str | None = None
    app_secret: str | None = None
    tenant_access_token: str | None = None
    user_access_token: str | None = None
    use_demo_when_missing_credentials: bool = True
    messages: FeishuMessageConfig = Field(default_factory=FeishuMessageConfig)
    calendar: FeishuCalendarConfig = Field(default_factory=FeishuCalendarConfig)


class SourcesConfig(BaseModel):
    git: GitSourceConfig = Field(default_factory=GitSourceConfig)
    feishu: FeishuSourceConfig = Field(default_factory=FeishuSourceConfig)


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


def _load_config_data(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path)
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def _get_nested(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _set_nested(data: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current: dict[str, Any] = data
    for key in path[:-1]:
        next_value = current.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            current[key] = next_value
        current = next_value
    current[path[-1]] = value


def load_config(path: Path | str = DEFAULT_CONFIG_PATH, *, expand_env: bool = True) -> AppConfig:
    data = _load_config_data(path)
    return AppConfig.model_validate(_expand_env(data) if expand_env else data)


def config_for_client(config: AppConfig) -> dict[str, Any]:
    data = config.model_dump(mode="json")
    for path in SECRET_FIELD_PATHS:
        # 密钥字段不回显到浏览器，避免页面源码、日志或截屏泄露。
        _set_nested(data, path, "")
    return data


def merge_runtime_secrets(incoming: AppConfig, current: AppConfig) -> AppConfig:
    data = incoming.model_dump(mode="json")
    current_data = current.model_dump(mode="json")
    for path in SECRET_FIELD_PATHS:
        incoming_value = _get_nested(data, path)
        if is_placeholder_secret(incoming_value):
            # 页面留空表示“沿用当前进程中的密钥”，不清空运行时凭证。
            _set_nested(data, path, _get_nested(current_data, path))
    return AppConfig.model_validate(data)


def save_config(config: AppConfig, path: Path | str = DEFAULT_CONFIG_PATH) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json")
    raw_data = _load_config_data(config_path) if config_path.exists() else {}
    raw_config = AppConfig.model_validate(raw_data)
    raw_config_data = raw_config.model_dump(mode="json")

    for secret_path in SECRET_FIELD_PATHS:
        # YAML 中始终保留原有占位符或原始值，页面输入的密钥只用于当前进程。
        _set_nested(data, secret_path, _get_nested(raw_config_data, secret_path))

    config_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
