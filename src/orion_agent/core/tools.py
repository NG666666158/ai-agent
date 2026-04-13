from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
from typing import Any

import httpx

from orion_agent.core.config import Settings
from orion_agent.core.models import ToolDefinition, ToolPermission


ToolHandler = Callable[..., str]


class ToolRegistry:
    """Minimal but structured tool registry for the MVP."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._handlers: dict[str, ToolHandler] = {
            "summarize_text": self._summarize_text,
            "read_local_file": self._read_local_file,
            "extract_keywords": self._extract_keywords,
            "web_search": self._web_search,
            "generate_markdown": self._generate_markdown,
        }
        self._definitions: dict[str, ToolDefinition] = {
            "summarize_text": ToolDefinition(
                name="summarize_text",
                description="压缩输入文本并返回简要摘要。",
                input_schema={"text": "string"},
                output_schema={"summary": "string"},
            ),
            "read_local_file": ToolDefinition(
                name="read_local_file",
                description="读取本地文本文件内容。",
                input_schema={"path": "string"},
                output_schema={"content": "string"},
            ),
            "extract_keywords": ToolDefinition(
                name="extract_keywords",
                description="从文本中提取关键词，用于规划和摘要。",
                input_schema={"text": "string"},
                output_schema={"keywords": "string"},
            ),
            "web_search": ToolDefinition(
                name="web_search",
                description="Search the public web for supporting information.",
                input_schema={"query": "string"},
                output_schema={"results": "string"},
                permission_level=ToolPermission.SAFE,
            ),
            "generate_markdown": ToolDefinition(
                name="generate_markdown",
                description="根据标题和章节生成 Markdown 文档。",
                input_schema={"title": "string", "sections": "array"},
                output_schema={"markdown": "string"},
                permission_level=ToolPermission.SAFE,
            ),
        }

    def list_definitions(self) -> list[ToolDefinition]:
        return list(self._definitions.values())

    def invoke(self, tool_name: str, **kwargs: Any) -> str:
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise ValueError(f"Unknown tool: {tool_name}")
        return handler(**kwargs)

    def _summarize_text(self, text: str) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) <= 180:
            return cleaned
        return f"{cleaned[:177]}..."

    def _read_local_file(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def _extract_keywords(self, text: str) -> str:
        words = [word.strip(".,:;()[]{}").lower() for word in text.split()]
        filtered: list[str] = []
        seen: set[str] = set()
        for word in words:
            if len(word) < 4 or word in seen:
                continue
            seen.add(word)
            filtered.append(word)
            if len(filtered) == 8:
                break
        return ", ".join(filtered)

    def _web_search(self, query: str) -> str:
        if not self.settings.allow_online_search:
            return json.dumps([], ensure_ascii=False)
        try:
            response = httpx.get(
                self.settings.web_search_endpoint,
                params={
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                },
                timeout=self.settings.web_search_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return json.dumps([], ensure_ascii=False)
        results: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        max_results = self.settings.web_search_max_results
        for item in payload.get("RelatedTopics", [])[: max_results + 2]:
            if "Text" in item and "FirstURL" in item:
                if item["FirstURL"] not in seen_urls:
                    results.append({"title": item["Text"], "url": item["FirstURL"]})
                    seen_urls.add(item["FirstURL"])
            elif "Topics" in item:
                for nested in item["Topics"][: max_results + 2]:
                    if "Text" in nested and "FirstURL" in nested and nested["FirstURL"] not in seen_urls:
                        results.append({"title": nested["Text"], "url": nested["FirstURL"]})
                        seen_urls.add(nested["FirstURL"])
            if len(results) >= max_results:
                break

        abstract = payload.get("AbstractText")
        abstract_url = payload.get("AbstractURL", "")
        if abstract and abstract_url not in seen_urls:
            results.insert(0, {"title": abstract, "url": abstract_url})
        return json.dumps(results[:max_results], ensure_ascii=False)

    def _generate_markdown(self, title: str, sections: list[dict[str, str]]) -> str:
        lines = [f"# {title}", ""]
        for section in sections:
            lines.append(f"## {section['heading']}")
            lines.append(section["content"])
            lines.append("")
        return "\n".join(lines).strip()
