from __future__ import annotations

import json
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
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("anthropic dependency is required for MiniMax provider") from exc
        self.client = Anthropic(
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
            max_retries=settings.minimax_max_retries,
        )

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if self._degraded:
            return self.fallback.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        try:
            content = self._complete(system_prompt=system_prompt, user_prompt=user_prompt, json_mode=True)
            return json.loads(content)
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
        prompt = self._build_prompt(user_prompt=user_prompt, json_mode=False)
        try:
            with self.client.messages.stream(
                model=self.settings.minimax_model,
                max_tokens=1_500,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}],
                    }
                ],
                timeout=self.settings.request_timeout,
            ) as stream:
                emitted = False
                for chunk in stream.text_stream:
                    if chunk:
                        emitted = True
                        yield chunk
                if not emitted:
                    raise RuntimeError("empty stream response")
        except Exception as exc:
            self._degraded = True
            self._last_error = f"{type(exc).__name__}: {exc}"
            yield from self.fallback.stream_text(system_prompt=system_prompt, user_prompt=user_prompt)

    def _complete(self, *, system_prompt: str, user_prompt: str, json_mode: bool) -> str:
        response = self.client.messages.create(
            model=self.settings.minimax_model,
            max_tokens=1_500,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": self._build_prompt(user_prompt=user_prompt, json_mode=json_mode)}],
                }
            ],
            timeout=self.settings.request_timeout,
        )
        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "".join(parts).strip()

    def _build_prompt(self, *, user_prompt: str, json_mode: bool) -> str:
        if not json_mode:
            return user_prompt
        return (
            f"{user_prompt}\n\n"
            "Return valid JSON only. Do not wrap the result in markdown fences."
        )

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
                "deliverable_title": "AI Agent MVP Delivery",
            }
        if "planner" in system_prompt.lower():
            include_web = "Web search allowed: True" in user_prompt
            has_source = "Has source material: True" in user_prompt
            steps: list[dict[str, Any]] = [
                {"name": "Parse Task", "description": "Clarify the task goal and constraints.", "tool_name": None},
                {"name": "Recall Memory", "description": "Review relevant short-term and long-term memory.", "tool_name": None},
            ]
            if has_source:
                steps.append(
                    {
                        "name": "Read Source Material",
                        "description": "Summarize provided material before planning.",
                        "tool_name": "read_local_file",
                    }
                )
            if include_web:
                steps.append(
                    {
                        "name": "Web Research",
                        "description": "Collect recent supporting information from the web.",
                        "tool_name": "web_search",
                    }
                )
            steps.extend(
                [
                    {"name": "Create Plan", "description": "Draft the implementation plan.", "tool_name": None},
                    {"name": "Draft Deliverable", "description": "Generate the final Markdown deliverable.", "tool_name": "generate_markdown"},
                    {"name": "Review Output", "description": "Validate completeness and quality.", "tool_name": None},
                ]
            )
            return {"steps": steps}
        if "ai reviewer" in system_prompt.lower():
            return {
                "passed": True,
                "summary": "Fallback reviewer accepted the deliverable.",
                "checklist": [
                    "Goal coverage: pass",
                    "Structured output: pass",
                    "Actionable implementation notes: pass",
                ],
            }
        if "memory writer" in system_prompt.lower():
            goal = self._extract_goal(user_prompt)
            return {
                "topic": goal[:80],
                "summary": f"Memory for task: {goal}",
                "details": user_prompt[-400:],
                "tags": ["agent", "mvp", "planning", *goal.lower().split()[:2]],
            }
        return {}

    def generate_text(self, *, system_prompt: str, user_prompt: str) -> str:
        return "".join(self.stream_text(system_prompt=system_prompt, user_prompt=user_prompt))

    def stream_text(self, *, system_prompt: str, user_prompt: str) -> Iterator[str]:
        goal = self._extract_goal(user_prompt)
        text = (
            "# AI Agent MVP Delivery\n\n"
            "## Goal\n"
            f"{goal}\n\n"
            "## Implementation Summary\n"
            "- Replaced the rule-based flow with prompt-driven orchestration.\n"
            "- Added tool usage, web research support, and long-term memory.\n"
            "- Preserved deterministic fallback behavior for local development.\n"
        )
        chunk_size = 48
        for index in range(0, len(text), chunk_size):
            yield text[index : index + chunk_size]

    def _extract_goal(self, payload: str) -> str:
        json_payload = self._extract_json_payload(payload)
        if "goal" in json_payload and isinstance(json_payload["goal"], str):
            return json_payload["goal"]
        lines = payload.splitlines()
        for index, line in enumerate(lines):
            if "goal" in line.lower():
                extracted = line.split(":", 1)[-1].strip().strip('",')
                if extracted:
                    return extracted
                for follow_line in lines[index + 1 :]:
                    cleaned = follow_line.strip().strip('",')
                    if cleaned:
                        return cleaned
        return "Complete the requested task"

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
            "last_error": "",
        }

    def probe(self) -> dict[str, Any]:
        return {
            "provider": "fallback",
            "status": "ready",
            "mode": "fallback",
            "preview": "fallback-active",
        }


def build_llm_client(settings: Settings) -> BaseLLMClient:
    if settings.force_fallback_llm:
        return FallbackLLMClient()
    if settings.llm_provider == "minimax" and settings.minimax_api_key:
        try:
            return MiniMaxLLMClient(settings)
        except Exception:
            return FallbackLLMClient()
    if settings.openai_api_key:
        return OpenAILLMClient(settings)
    return FallbackLLMClient()
