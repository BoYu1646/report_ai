from __future__ import annotations

from collections import Counter
from datetime import datetime

from src.config import AppConfig, DEFAULT_REPORT_TEMPLATE, is_placeholder_secret
from src.models import WorkItem


SECTION_TITLES = {
    "done": "本周完成",
    "in_progress": "进行中",
    "risks": "风险/阻塞",
    "next_week": "下周计划",
}


class WeeklyReportAgent:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    async def generate(
        self,
        items: list[WorkItem],
        week_start: datetime,
        week_end: datetime,
        template: str | None = None,
    ) -> tuple[str, bool]:
        if not is_placeholder_secret(self.config.llm.api_key):
            try:
                return await self._generate_with_langchain(items, week_start, week_end, template), True
            except Exception as exc:
                fallback = self._generate_fallback(items, week_start, week_end, template)
                return f"{fallback}\n\n> 备注：LLM 调用失败，已使用本地兜底生成。错误：`{exc}`\n", False
        return self._generate_fallback(items, week_start, week_end, template), False

    async def _generate_with_langchain(
        self,
        items: list[WorkItem],
        week_start: datetime,
        week_end: datetime,
        template: str | None,
    ) -> str:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=self.config.llm.model,
            api_key=self.config.llm.api_key,
            base_url=self.config.llm.base_url,
            temperature=self.config.llm.temperature,
            timeout=self.config.llm.timeout_seconds,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是资深研发效能专家。请基于给定的真实工作项生成中文 Markdown 周报。"
                    "必须包含：本周完成、进行中、风险/阻塞、下周计划。"
                    "本周必须严格等于输入的自然周周期，禁止使用最近 7 天作为时间范围。"
                    "不得编造未在数据源出现的事实；不确定的事项使用待确认表述；尽量保留来源链接。",
                ),
                (
                    "human",
                    "周报标题：{title}\n自然周周期：{week_start} 至 {week_end}\n"
                    "请优先遵循以下自定义模板输出，模板中的占位符可按语义替换为真实内容：\n{template}\n\n"
                    "必需章节：{sections}\n工作项 JSON：\n{items}",
                ),
            ]
        )
        chain = prompt | llm | StrOutputParser()
        markdown = await chain.ainvoke(
            {
                "title": self.config.report.title,
                "week_start": week_start.strftime("%Y-%m-%d %H:%M:%S"),
                "week_end": week_end.strftime("%Y-%m-%d %H:%M:%S"),
                "template": self._template(template),
                "sections": ", ".join(SECTION_TITLES.get(section, section) for section in self.config.report.sections),
                "items": "[" + ",\n".join(item.model_dump_json() for item in items) + "]",
            }
        )
        return self._ensure_required_sections(markdown)

    def _generate_fallback(
        self,
        items: list[WorkItem],
        week_start: datetime,
        week_end: datetime,
        template: str | None,
    ) -> str:
        completed = [
            item
            for item in items
            if item.type in {"commit", "message", "calendar_event"}
            or item.status in {"merged", "closed", "committed", "updated", "sent"}
        ]
        in_progress = [item for item in items if item.status in {"open", "draft"}]
        risks = [
            item
            for item in items
            if item.status == "open"
            or "risk" in [str(label).lower() for label in item.metadata.get("labels", [])]
            or "阻塞" in item.title
        ]
        source_counts = Counter(item.source for item in items)
        repo_counts = Counter(item.repo for item in items if item.repo)

        done_md = self._format_block(completed, empty="暂无明确完成项，建议检查本自然周内是否存在有效数据。")
        in_progress_md = self._format_block(in_progress, empty="暂无打开状态的 PR / Issue。")
        risks_md = self._format_block(risks, empty="暂无明显风险；仍建议关注长期未关闭 Issue 与外部依赖。")
        if in_progress:
            next_week_md = "\n".join(f"- 跟进：{item.title}{self._link_suffix(item)}" for item in in_progress[:8])
        elif repo_counts:
            next_week_md = "\n".join(f"- 继续推进 `{repo}` 相关交付与质量验证。" for repo in repo_counts.keys())
        else:
            next_week_md = "- 待确认下周重点任务，并补充项目计划来源。"

        # 本地兜底同样渲染自定义模板，保证无模型 Key 时也能验证模板配置效果。
        rendered = self._template(template).format_map(
            _SafeDict(
                title=self.config.report.title,
                generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                week_start=week_start.strftime("%Y-%m-%d %H:%M:%S"),
                week_end=week_end.strftime("%Y-%m-%d %H:%M:%S"),
                git_count=str(source_counts.get("git", 0)),
                feishu_count=str(source_counts.get("feishu", 0)),
                done=done_md,
                in_progress=in_progress_md,
                risks=risks_md,
                next_week=next_week_md,
                sources="\n".join(
                    f"- `{item.source}/{item.type}`：{item.title}{self._link_suffix(item)}" for item in items[:30]
                )
                or "- 暂无数据来源。",
            )
        )
        return self._ensure_required_sections(rendered)

    def _ensure_required_sections(self, markdown: str) -> str:
        output = markdown.strip()
        for title in SECTION_TITLES.values():
            if f"## {title}" not in output and f"# {title}" not in output:
                output += f"\n\n## {title}\n- 待补充。"
        return output + "\n"

    def _format_items(self, items: list[WorkItem], empty: str) -> list[str]:
        if not items:
            return [f"- {empty}"]
        return [f"- [{item.source}/{item.type}] {item.title}{self._link_suffix(item)}" for item in items[:12]]

    def _format_block(self, items: list[WorkItem], empty: str) -> str:
        return "\n".join(self._format_items(items, empty))

    def _template(self, override: str | None) -> str:
        return override or self.config.report.template or DEFAULT_REPORT_TEMPLATE

    @staticmethod
    def _link_suffix(item: WorkItem) -> str:
        return f"（[来源]({item.url})）" if item.url else ""


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
