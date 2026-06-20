from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from typing import Any

from src.config import AppConfig, DEFAULT_REPORT_TEMPLATE, is_placeholder_secret
from src.models import WorkItem


SECTION_TITLES = {
    "summary": "本周概览",
    "highlights": "重点成果",
    "done": "本周完成",
    "in_progress": "进行中",
    "risks": "风险/阻塞",
    "next_week": "下周计划",
    "details": "工作明细",
}

SUMMARY_SECTIONS = ("本周概览", "重点成果", "本周完成", "进行中", "风险/阻塞", "下周计划", "工作明细")


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
        optimized_items = await self._optimize_task_descriptions(items, llm, ChatPromptTemplate, StrOutputParser)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是资深研发效能专家和研发团队负责人，擅长把 Git、飞书消息、日程等零散记录归纳成结构清晰的管理周报。"
                    "请先对真实工作项做主题聚类、去重、归纳，再生成中文 Markdown 周报，禁止把原始数据简单逐条罗列。"
                    "必须包含：本周概览、重点成果、本周完成、进行中、风险/阻塞、下周计划、工作明细。"
                    "本周必须严格等于输入的自然周周期，禁止使用最近 7 天作为时间范围。"
                    "不得编造未在数据源出现的事实；不确定的事项使用待确认表述；尽量保留来源链接。"
                    "工作项中的 description 已由大模型基于原始标题和上下文优化，输出时优先使用 description，"
                    "但不得改变原始事实、状态、时间、作者和来源链接。"
                    "写作要求：1）本周概览用 3-5 条总结整体进展和数据覆盖；"
                    "2）重点成果用“成果/价值/证据”表达；"
                    "3）本周完成按主题分组，每组说明完成了什么、解决了什么问题、依据哪些记录；"
                    "4）进行中和风险要说明状态、影响和建议动作；"
                    "5）下周计划要从未关闭事项、风险和本周主题自然推导；"
                    "6）工作明细可以列证据，但必须服务于前面的归纳结论。"
                    "对于纯数字、单字测试、无效卡片 JSON 等低信息量消息，只作为数据来源证据，不要当成成果。",
                ),
                (
                    "human",
                    "周报标题：{title}\n自然周周期：{week_start} 至 {week_end}\n"
                    "请优先遵循以下自定义模板输出，模板中的占位符可按语义替换为真实内容：\n{template}\n\n"
                    "必需章节：{sections}\n数据概览：{source_summary}\n"
                    "工作项 JSON（原始记录仅作为证据，请先归纳再输出）：\n{items}",
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
                "sections": "、".join(SUMMARY_SECTIONS),
                "source_summary": self._source_summary(optimized_items),
                "items": self._items_json(optimized_items),
            }
        )
        return self._ensure_required_sections(markdown)

    async def _optimize_task_descriptions(
        self,
        items: list[WorkItem],
        llm: Any,
        chat_prompt_template: Any,
        output_parser: Any,
    ) -> list[WorkItem]:
        if not items:
            return items

        prompt = chat_prompt_template.from_messages(
            [
                (
                    "system",
                    "你是资深大模型应用开发工程师，擅长把零散研发记录改写成日报/周报中的任务描述。"
                    "请只基于输入事实优化表达，不补充未出现的业务结论、进度、负责人或时间。"
                    "每条 description 使用中文，控制在 50 到 120 字，动宾结构优先，突出交付动作和结果。"
                    "如信息不足，保留待确认语气。只输出 JSON 数组，不输出 Markdown 或解释。",
                ),
                (
                    "human",
                    "请为以下工作项生成优化后的任务描述。每个元素必须包含 index 与 description：\n{items}",
                ),
            ]
        )
        chain = prompt | llm | output_parser()
        try:
            raw = await chain.ainvoke({"items": self._items_json(items)})
        except Exception:
            return items
        descriptions = self._parse_optimized_descriptions(raw)
        if not descriptions:
            return items

        optimized: list[WorkItem] = []
        for index, item in enumerate(items):
            description = descriptions.get(index)
            if description:
                optimized.append(item.model_copy(update={"description": description}))
            else:
                optimized.append(item)
        return optimized

    def _parse_optimized_descriptions(self, raw: str) -> dict[int, str]:
        text = raw.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            payload = payload.get("items") or payload.get("descriptions")
        if not isinstance(payload, list):
            return {}

        descriptions: dict[int, str] = {}
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            index = entry.get("index")
            description = entry.get("description")
            if not isinstance(index, int) or not isinstance(description, str):
                continue
            description = " ".join(description.split())
            if description:
                descriptions[index] = description[:200]
        return descriptions

    def _generate_fallback(
        self,
        items: list[WorkItem],
        week_start: datetime,
        week_end: datetime,
        template: str | None,
    ) -> str:
        themes = self._group_by_theme(items)
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

        executive_summary_md = self._format_executive_summary(items, themes, source_counts)
        highlights_md = self._format_highlights(themes)
        done_md = self._format_done_by_theme(themes, empty="暂无明确完成项，建议检查本自然周内是否存在有效数据。")
        in_progress_md = self._format_block(in_progress, empty="暂无打开状态的 PR / Issue。")
        risks_md = self._format_block(risks, empty="暂无明显风险；仍建议关注长期未关闭 Issue 与外部依赖。")
        if in_progress:
            next_week_md = "\n".join(f"- 跟进：{self._display_text(item)}{self._link_suffix(item)}" for item in in_progress[:8])
        elif repo_counts:
            next_week_md = "\n".join(f"- 继续推进 `{repo}` 相关交付与质量验证。" for repo in repo_counts.keys())
        elif themes:
            next_week_md = "\n".join(f"- 围绕「{theme}」继续补充验收结果、风险状态和后续计划。" for theme in list(themes)[:5])
        else:
            next_week_md = "- 待确认下周重点任务，并补充项目计划来源。"
        details_md = self._format_details_by_theme(themes)

        # 本地兜底同样渲染自定义模板，保证无模型 Key 时也能验证模板配置效果。
        rendered = self._template(template).format_map(
            _SafeDict(
                title=self.config.report.title,
                generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                week_start=week_start.strftime("%Y-%m-%d %H:%M:%S"),
                week_end=week_end.strftime("%Y-%m-%d %H:%M:%S"),
                git_count=str(source_counts.get("git", 0)),
                feishu_count=str(source_counts.get("feishu", 0)),
                executive_summary=executive_summary_md,
                highlights=highlights_md,
                done=done_md,
                in_progress=in_progress_md,
                risks=risks_md,
                next_week=next_week_md,
                details=details_md,
                sources="\n".join(
                    f"- `{item.source}/{item.type}`：{self._display_text(item)}{self._link_suffix(item)}"
                    for item in items[:30]
                )
                or "- 暂无数据来源。",
            )
        )
        return self._ensure_required_sections(rendered)

    def _ensure_required_sections(self, markdown: str) -> str:
        output = markdown.strip()
        for title in SUMMARY_SECTIONS:
            if f"## {title}" not in output and f"# {title}" not in output:
                output += f"\n\n## {title}\n- 待补充。"
        return output + "\n"

    def _group_by_theme(self, items: list[WorkItem]) -> dict[str, list[WorkItem]]:
        themes: dict[str, list[WorkItem]] = {}
        meaningful_items = [item for item in items if not self._is_low_signal(item)]
        for item in meaningful_items or items:
            theme = self._theme_name(item)
            themes.setdefault(theme, []).append(item)
        return dict(sorted(themes.items(), key=lambda pair: len(pair[1]), reverse=True))

    def _theme_name(self, item: WorkItem) -> str:
        text = self._display_text(item)
        lowered = text.lower()
        if item.repo:
            return f"{item.repo} 研发交付"
        if item.type == "calendar_event":
            return "会议沟通与计划确认"
        if any(keyword in lowered for keyword in ("risk", "风险", "阻塞", "失败", "error", "bug", "修复", "fix")):
            return "风险问题处理"
        if any(keyword in lowered for keyword in ("测试", "test", "验证", "验收")):
            return "测试验证与质量保障"
        if any(keyword in lowered for keyword in ("配置", "权限", "token", "凭证", "密钥", "认证")):
            return "配置权限与集成联调"
        if item.source == "feishu":
            return "飞书沟通与任务同步"
        return "日常研发推进"

    def _format_executive_summary(
        self, items: list[WorkItem], themes: dict[str, list[WorkItem]], source_counts: Counter[str]
    ) -> str:
        if not items:
            return "- 本周暂无可归纳的有效工作记录，建议补充 Git、飞书消息或日程数据源。"
        low_signal_count = sum(1 for item in items if self._is_low_signal(item))
        lines = [
            f"- 本周共采集 {len(items)} 条工作记录，其中 Git {source_counts.get('git', 0)} 条、飞书 {source_counts.get('feishu', 0)} 条。",
            f"- 工作主要集中在：{'、'.join(list(themes)[:4])}。",
        ]
        top_theme, top_items = next(iter(themes.items()))
        lines.append(f"- 核心推进方向为「{top_theme}」，关联 {len(top_items)} 条证据记录。")
        if low_signal_count:
            lines.append(f"- 已识别 {low_signal_count} 条低信息量测试/占位消息，归纳时不作为成果依据，仅保留在数据来源中。")
        if len(themes) > 1:
            lines.append("- 已将原始消息、提交、日程按主题聚合，以下章节优先展示归纳结论并保留关键证据。")
        return "\n".join(lines)

    def _format_highlights(self, themes: dict[str, list[WorkItem]]) -> str:
        if not themes:
            return "- 暂无明确重点成果。"
        lines = []
        for theme, theme_items in list(themes.items())[:5]:
            evidence = "；".join(self._evidence_text(item) for item in theme_items[:3])
            lines.append(f"- **{theme}**：归纳 {len(theme_items)} 条记录，形成阶段性推进；证据：{evidence}。")
        return "\n".join(lines)

    def _format_done_by_theme(self, themes: dict[str, list[WorkItem]], empty: str) -> str:
        if not themes:
            return f"- {empty}"
        blocks = []
        for theme, theme_items in list(themes.items())[:6]:
            evidence = "；".join(self._evidence_text(item) for item in theme_items[:4])
            blocks.append(f"- **{theme}**：完成/推进 {len(theme_items)} 项相关工作，主要包括：{evidence}。")
        return "\n".join(blocks)

    def _format_details_by_theme(self, themes: dict[str, list[WorkItem]]) -> str:
        if not themes:
            return "- 暂无工作明细。"
        blocks = []
        for theme, theme_items in list(themes.items())[:6]:
            lines = [f"### {theme}"]
            for item in theme_items[:8]:
                lines.append(f"- [{item.source}/{item.type}] {self._evidence_text(item)}{self._link_suffix(item)}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def _format_items(self, items: list[WorkItem], empty: str) -> list[str]:
        if not items:
            return [f"- {empty}"]
        return [f"- [{item.source}/{item.type}] {self._display_text(item)}{self._link_suffix(item)}" for item in items[:12]]

    def _format_block(self, items: list[WorkItem], empty: str) -> str:
        return "\n".join(self._format_items(items, empty))

    def _template(self, override: str | None) -> str:
        return override or self.config.report.template or DEFAULT_REPORT_TEMPLATE

    @staticmethod
    def _display_text(item: WorkItem) -> str:
        return WeeklyReportAgent._clean_text(item.description or item.title)

    @staticmethod
    def _evidence_text(item: WorkItem) -> str:
        text = WeeklyReportAgent._display_text(item)
        return text if len(text) <= 120 else f"{text[:120]}..."

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = text.strip()
        if cleaned == "[Invalid calendar JSON]":
            return "飞书日历卡片内容待解析"
        todo_match = re.search(r"<todo[^>]*>(.*?)</todo>", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if todo_match:
            cleaned = todo_match.group(1)
        calendar_match = re.search(r"<calendar_share[^>]*>(.*)", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if calendar_match:
            cleaned = calendar_match.group(1)
        cleaned = re.sub(r"</?[a-zA-Z_][^>]*>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or text.strip()

    @classmethod
    def _is_low_signal(cls, item: WorkItem) -> bool:
        if item.source != "feishu" or item.type != "message":
            return False
        text = cls._clean_text(item.description or item.title).strip().lower()
        if text in {"test", "测试", "1", "12", "111", "888", "999", "000"}:
            return True
        if text.isdigit() and len(text) <= 8:
            return True
        if "invalid calendar json" in text or text == "飞书日历卡片内容待解析":
            return True
        return False

    @classmethod
    def _items_json(cls, items: list[WorkItem]) -> str:
        payload = []
        for index, item in enumerate(items):
            data = item.model_dump(mode="json", exclude_none=True)
            data["index"] = index
            for key in ("title", "description", "author", "repo", "chat_name", "status", "url"):
                if key in data:
                    data[key] = cls._compact_value(data[key])
            if "metadata" in data:
                data["metadata"] = cls._compact_value(data["metadata"])
            payload.append(data)
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _source_summary(items: list[WorkItem]) -> str:
        if not items:
            return "无工作项。"
        source_counts = Counter(item.source for item in items)
        type_counts = Counter(item.type for item in items)
        repo_counts = Counter(item.repo for item in items if item.repo)
        parts = [
            f"共 {len(items)} 条",
            "来源：" + "、".join(f"{source} {count} 条" for source, count in source_counts.items()),
            "类型：" + "、".join(f"{item_type} {count} 条" for item_type, count in type_counts.items()),
        ]
        if repo_counts:
            parts.append("仓库：" + "、".join(f"{repo} {count} 条" for repo, count in repo_counts.items()))
        return "；".join(parts)

    @classmethod
    def _compact_value(cls, value: Any, *, max_chars: int = 800) -> Any:
        if isinstance(value, str):
            text = " ".join(value.split())
            return text if len(text) <= max_chars else f"{text[:max_chars]}..."
        if isinstance(value, list):
            return [cls._compact_value(item, max_chars=max_chars) for item in value[:20]]
        if isinstance(value, dict):
            return {
                key: cls._compact_value(item, max_chars=max_chars)
                for key, item in list(value.items())[:20]
            }
        return value

    @staticmethod
    def _link_suffix(item: WorkItem) -> str:
        return f"（[来源]({item.url})）" if item.url else ""


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
