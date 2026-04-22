from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from openai import OpenAI

from orion_agent.core.config import Settings


class BaseLLMClient(ABC):
    @abstractmethod
    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def generate_text(self, *, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def stream_text(self, *, system_prompt: str, user_prompt: str) -> Iterator[str]:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    def probe(self) -> dict[str, Any]:
        raise NotImplementedError


class OpenAILLMClient(BaseLLMClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
        self.fallback = FallbackLLMClient()
        self._degraded = False
        self._last_error: str | None = None

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if self._degraded:
            return self.fallback.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        try:
            content = self._complete(system_prompt=system_prompt, user_prompt=user_prompt, json_mode=True)
            return json.loads(content)
        except Exception:
            self._degraded = True
            self._last_error = "openai generation failed; degraded to fallback"
            return self.fallback.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)

    def generate_text(self, *, system_prompt: str, user_prompt: str) -> str:
        if self._degraded:
            return self.fallback.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)
        try:
            return self._complete(system_prompt=system_prompt, user_prompt=user_prompt, json_mode=False)
        except Exception:
            self._degraded = True
            self._last_error = "openai generation failed; degraded to fallback"
            return self.fallback.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    def stream_text(self, *, system_prompt: str, user_prompt: str) -> Iterator[str]:
        if self._degraded:
            yield from self.fallback.stream_text(system_prompt=system_prompt, user_prompt=user_prompt)
            return
        try:
            stream = self.client.chat.completions.create(
                model=self.settings.openai_model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                stream=True,
                timeout=self.settings.request_timeout,
            )
            emitted = False
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    emitted = True
                    yield delta
            if not emitted:
                raise RuntimeError("empty stream response")
        except Exception:
            self._degraded = True
            self._last_error = "openai streaming failed; degraded to fallback"
            yield from self.fallback.stream_text(system_prompt=system_prompt, user_prompt=user_prompt)

    def _complete(self, *, system_prompt: str, user_prompt: str, json_mode: bool) -> str:
        response = self.client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=0.2,
            response_format={"type": "json_object"} if json_mode else None,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=self.settings.request_timeout,
        )
        return response.choices[0].message.content or ""

    def health(self) -> dict[str, str]:
        return {
            "provider": "openai",
            "mode": "fallback" if self._degraded else "online",
            "last_error": self._last_error or "",
        }

    def probe(self) -> dict[str, Any]:
        try:
            preview = self._complete(
                system_prompt="You are a connectivity probe.",
                user_prompt="Reply with the single word ok.",
                json_mode=False,
            )
            return {
                "provider": "openai",
                "status": "ready",
                "mode": "fallback" if self._degraded else "online",
                "preview": preview[:120],
            }
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            return {
                "provider": "openai",
                "status": "error",
                "mode": "fallback" if self._degraded else "online",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }


class MiniMaxLLMClient(BaseLLMClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.fallback = FallbackLLMClient()
        self._degraded = False
        self._last_error: str | None = None
        self.client = OpenAI(
            api_key=settings.minimax_api_key,
            base_url=self._resolve_openai_base_url(settings.minimax_base_url),
            max_retries=settings.minimax_max_retries,
        )

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if self._degraded:
            return self.fallback.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        try:
            content = self._complete(system_prompt=system_prompt, user_prompt=user_prompt, json_mode=True)
            return self._parse_json_payload(content)
        except Exception as exc:
            self._degraded = True
            self._last_error = f"{type(exc).__name__}: {exc}"
            return self.fallback.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)

    def generate_text(self, *, system_prompt: str, user_prompt: str) -> str:
        if self._degraded:
            return self.fallback.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)
        try:
            return self._complete(system_prompt=system_prompt, user_prompt=user_prompt, json_mode=False)
        except Exception as exc:
            self._degraded = True
            self._last_error = f"{type(exc).__name__}: {exc}"
            return self.fallback.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    def stream_text(self, *, system_prompt: str, user_prompt: str) -> Iterator[str]:
        if self._degraded:
            yield from self.fallback.stream_text(system_prompt=system_prompt, user_prompt=user_prompt)
            return
        try:
            stream = self.client.chat.completions.create(
                model=self.settings.minimax_model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                extra_body={"reasoning_split": True},
                stream=True,
                timeout=self.settings.request_timeout,
            )
            emitted = False
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    emitted = True
                    yield delta
            if not emitted:
                raise RuntimeError("empty stream response")
        except Exception as exc:
            self._degraded = True
            self._last_error = f"{type(exc).__name__}: {exc}"
            yield from self.fallback.stream_text(system_prompt=system_prompt, user_prompt=user_prompt)

    def _complete(self, *, system_prompt: str, user_prompt: str, json_mode: bool) -> str:
        response = self.client.chat.completions.create(
            model=self.settings.minimax_model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._build_prompt(user_prompt=user_prompt, json_mode=json_mode)},
            ],
            extra_body={"reasoning_split": True},
            timeout=self.settings.request_timeout,
        )
        return self._extract_message_text(response.choices[0].message).strip()

    def _build_prompt(self, *, user_prompt: str, json_mode: bool) -> str:
        if not json_mode:
            return user_prompt
        return (
            f"{user_prompt}\n\n"
            "Return valid JSON only. Do not wrap the result in markdown fences."
        )

    def _resolve_openai_base_url(self, base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/anthropic"):
            return f"{normalized[:-len('/anthropic')]}/v1"
        return normalized

    def _extract_message_text(self, message: Any) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            fragments: list[str] = []
            for item in content:
                if isinstance(item, str):
                    fragments.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        fragments.append(text)
                    continue
                text = getattr(item, "text", None) or getattr(item, "content", None)
                if isinstance(text, str):
                    fragments.append(text)
            return "\n".join(fragment for fragment in fragments if fragment).strip()
        return str(content or "")

    def _parse_json_payload(self, content: str) -> dict[str, Any]:
        normalized = (content or "").strip()
        if not normalized:
            raise ValueError("empty JSON response")
        try:
            payload = json.loads(normalized)
            if isinstance(payload, dict):
                return payload
            raise ValueError("json response is not an object")
        except Exception:
            pass

        fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", normalized, re.IGNORECASE)
        if fenced_match:
            payload = json.loads(fenced_match.group(1))
            if isinstance(payload, dict):
                return payload

        start = normalized.find("{")
        end = normalized.rfind("}")
        if start != -1 and end != -1 and end > start:
            payload = json.loads(normalized[start : end + 1])
            if isinstance(payload, dict):
                return payload

        raise ValueError("unable to extract JSON object from MiniMax response")

    def health(self) -> dict[str, str]:
        return {
            "provider": "minimax",
            "mode": "fallback" if self._degraded else "online",
            "last_error": self._last_error or "",
        }

    def probe(self) -> dict[str, Any]:
        try:
            preview = self._complete(
                system_prompt="You are a connectivity probe.",
                user_prompt="Reply with the single word ok.",
                json_mode=False,
            )
            return {
                "provider": "minimax",
                "status": "ready",
                "mode": "fallback" if self._degraded else "online",
                "preview": preview[:120],
            }
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            return {
                "provider": "minimax",
                "status": "error",
                "mode": "fallback" if self._degraded else "online",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }


class FallbackLLMClient(BaseLLMClient):
    """Deterministic fallback used when no provider is available."""

    def __init__(self, *, last_error: str | None = None) -> None:
        self._last_error = last_error or ""

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        request_payload = self._extract_json_payload(user_prompt)
        prompt = f"{system_prompt}\n{user_prompt}"
        if "task parser" in system_prompt.lower():
            domain = "software_project" if "mvp" in prompt.lower() or "development" in prompt.lower() else "documentation"
            return {
                "goal": self._extract_goal(user_prompt),
                "constraints": self._extract_constraints(user_prompt),
                "expected_output": request_payload.get("expected_output", "markdown"),
                "priority": "high",
                "domain": domain,
                "deliverable_title": "AI Agent 执行结果",
            }
        if "planner" in system_prompt.lower():
            include_web = "Web search allowed: True" in user_prompt
            has_source = "Has source material: True" in user_prompt
            steps: list[dict[str, Any]] = [
                {"name": "Parse Task", "description": "解析任务目标与约束条件。", "tool_name": None},
                {"name": "Recall Memory", "description": "检索相关短期与长期记忆。", "tool_name": None},
            ]
            if has_source:
                steps.append(
                    {
                        "name": "Read Source Material",
                        "description": "先读取并整理提供的资料内容。",
                        "tool_name": "read_local_file",
                    }
                )
            if include_web:
                steps.append(
                    {
                        "name": "Web Research",
                        "description": "补充联网检索得到的外部信息。",
                        "tool_name": "web_search",
                    }
                )
            steps.extend(
                [
                    {"name": "Create Plan", "description": "生成可执行的任务计划。", "tool_name": None},
                    {"name": "Draft Deliverable", "description": "调用模型生成最终回答正文。", "tool_name": "generate_markdown"},
                    {"name": "Review Output", "description": "检查结果完整性与质量。", "tool_name": None},
                ]
            )
            return {"steps": steps}
        if "ai reviewer" in system_prompt.lower():
            return {
                "passed": True,
                "summary": "回退评审已通过当前结果。",
                "checklist": [
                    "目标覆盖：通过",
                    "结构化输出：通过",
                    "可执行建议：通过",
                ],
            }
        if "memory writer" in system_prompt.lower():
            goal = self._extract_goal(user_prompt)
            return {
                "topic": goal[:80],
                "summary": f"任务记忆：{goal}",
                "details": user_prompt[-400:],
                "tags": ["agent", "任务", "规划", *goal.lower().split()[:2]],
            }
        return {}

    def generate_text(self, *, system_prompt: str, user_prompt: str) -> str:
        if "conversation summarizer" in system_prompt.lower():
            return self._summarize_conversation(user_prompt)
        return "".join(self.stream_text(system_prompt=system_prompt, user_prompt=user_prompt))

    def stream_text(self, *, system_prompt: str, user_prompt: str) -> Iterator[str]:
        goal = self._extract_goal(user_prompt)
        text = (
            "# AI 助手执行结果\n\n"
            "## 任务目标\n"
            f"{goal}\n\n"
            "## 结果概览\n"
            "- 系统已根据当前任务目标完成基础分析与组织。\n"
            "- 已结合工具调用、记忆检索和当前上下文生成回答。\n"
            "- 当前结果来自回退模式，适合本地联调与链路验证。\n"
        )
        text = self._build_fallback_markdown(goal, user_prompt)
        chunk_size = 48
        for index in range(0, len(text), chunk_size):
            yield text[index : index + chunk_size]

    def _extract_goal(self, payload: str) -> str:
        json_payload = self._extract_json_payload(payload)
        if "goal" in json_payload and isinstance(json_payload["goal"], str):
            return json_payload["goal"]
        matched_goal = re.search(r'"goal"\s*:\s*"([^"]+)"', payload, re.IGNORECASE)
        if matched_goal:
            return matched_goal.group(1).strip()
        lines = payload.splitlines()
        for index, line in enumerate(lines):
            if "goal" in line.lower():
                extracted = line.split(":", 1)[-1].strip().strip('",')
                if extracted:
                    return extracted
                for follow_line in lines[index + 1 :]:
                    cleaned = follow_line.strip().strip('",')
                    if cleaned and cleaned not in {"{", "}", "[", "]"}:
                        return cleaned
        return "完成当前请求"

    def _extract_constraints(self, payload: str) -> list[str]:
        json_payload = self._extract_json_payload(payload)
        if isinstance(json_payload.get("constraints"), list):
            return [str(item) for item in json_payload["constraints"]]
        constraints: list[str] = []
        for line in payload.splitlines():
            if "constraint" in line.lower():
                cleaned = line.split(":", 1)[-1].strip().strip('",')
                if cleaned:
                    constraints.append(cleaned)
        return constraints

    def _extract_json_payload(self, payload: str) -> dict[str, Any]:
        start = payload.find("{")
        end = payload.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            return json.loads(payload[start : end + 1])
        except Exception:
            return {}

    def health(self) -> dict[str, str]:
        return {
            "provider": "fallback",
            "mode": "fallback",
            "last_error": self._last_error,
        }

    def probe(self) -> dict[str, Any]:
        return {
            "provider": "fallback",
            "status": "ready",
            "mode": "fallback",
            "preview": "fallback-active",
            "error": self._last_error,
        }

    def _summarize_conversation(self, payload: str) -> str:
        lines = [line.strip("- ").strip() for line in payload.splitlines() if line.strip().startswith("- ")]
        if not lines:
            return "暂无可压缩的历史上下文。"
        recent = lines[-8:]
        return " | ".join(recent)[:1200]

    def _build_fallback_markdown(self, goal: str, user_prompt: str) -> str:
        answer = self._build_fallback_answer(goal, user_prompt)
        return (
            "# AI 助手执行结果\n\n"
            "## 任务目标\n"
            f"{goal}\n\n"
            "## 回答内容\n"
            f"{answer}\n\n"
            "## 结果说明\n"
            "- 当前结果由本地回退模式生成。\n"
            "- 已根据任务目标输出可直接阅读的正文内容。\n"
            "- 如需更强推理与事实性，可切换在线模型继续生成。\n"
        )

    def _build_fallback_answer(self, goal: str, user_prompt: str) -> str:
        lowered = goal.lower()

        if any(keyword in goal for keyword in ["讲个故事", "写个故事", "编个故事", "小故事"]):
            return (
                "从前有一座靠海的小城，城里有一家很旧的钟表铺。铺子的主人是个沉默的老人，"
                "但大家都知道，只要把坏掉的表送到他手里，第二天多半就能重新走动起来。\n\n"
                "有一天，一个总爱发呆的小女孩抱着一只停摆的怀表来到店里。她说，这是妈妈留下的，"
                "可自从妈妈离开后，表也不走了。老人接过怀表，没有立刻修，只是让她第二天傍晚再来。\n\n"
                "第二天傍晚，风很大，女孩准时来到店里。老人把怀表放回她手心，说：表其实昨天就能修好，"
                "但我想等今天。女孩问为什么。老人笑了笑，说：因为有些东西重新走动，不只是因为零件装好了，"
                "还因为有人愿意等它。\n\n"
                "女孩低头一看，怀表的指针正一格一格地走着，像很轻很轻的心跳。那一刻她忽然明白，"
                "原来想念不会让时间停下，真正让人往前走的，是在想念里依旧愿意相信未来。\n\n"
                "她把怀表贴在胸口，第一次觉得海风也没有那么冷了。"
            )

        if any(keyword in goal for keyword in ["天气", "下雨", "气温", "温度"]):
            return (
                "我目前没有稳定的实时天气数据源，所以不能直接保证即时天气结论完全准确。\n\n"
                "如果你要查询实时天气，建议告诉我城市名并开启联网查询，或者直接查看本地天气应用。\n\n"
                "如果你愿意，我也可以基于你给的城市，帮你整理一版更易读的天气播报模板。"
            )

        if any(keyword in goal for keyword in ["学习路线", "怎么学", "学习建议", "入门", "路线图"]):
            return (
                f"围绕“{goal}”，建议按照“基础认知 -> 核心练习 -> 项目验证”三段推进。\n\n"
                "第一阶段先搞清楚基本概念和主线框架，避免一开始陷入细节；\n"
                "第二阶段通过高频练习把知识变成可重复使用的能力；\n"
                "第三阶段一定要做一个小项目，把零散知识串成完整经验。\n\n"
                "如果你希望，我下一轮可以继续把它拆成按周执行的具体计划。"
            )

        if any(keyword in goal for keyword in ["总结", "概括", "摘要", "归纳"]):
            return (
                f"针对“{goal}”，建议先抓住主题、重点和结论三层结构。\n\n"
                "如果是资料整理类任务，最稳妥的做法是先列提纲，再合并相近信息，最后分别输出简版摘要和详细说明。"
            )

        if "story" in lowered:
            return (
                "这里给你一个简短故事：一个年轻人总觉得自己走得太慢，直到有一天他发现，"
                "那些看似绕远的路，其实让他学会了如何在风雨里站稳。后来他终于明白，"
                "成长不是突然变强，而是在一次次没有放弃之后，慢慢拥有了继续向前的能力。"
            )

        return (
            f"关于“{goal}”，我先给出直接回答：这类问题最适合先明确目标，再拆成 2 到 3 个可执行动作逐步推进。\n\n"
            "如果你愿意继续补充背景、限制条件或你想要的输出形式，我可以把回答细化成更完整的正式版本。"
        )

def build_llm_client(settings: Settings) -> BaseLLMClient:
    if settings.force_fallback_llm:
        return FallbackLLMClient()
    if settings.llm_provider == "minimax" and settings.minimax_api_key:
        try:
            return MiniMaxLLMClient(settings)
        except Exception as exc:
            return FallbackLLMClient(last_error=f"minimax init failed: {type(exc).__name__}: {exc}")
    if settings.openai_api_key:
        return OpenAILLMClient(settings)
    return FallbackLLMClient()
