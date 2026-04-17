from __future__ import annotations

import re

from orion_agent.core.models import UserProfileFact, UserProfileFactStatus
from orion_agent.core.repository import TaskRepository


class UserProfileManager:
    """Stores stable user preferences and retrieves relevant profile facts."""

    LANGUAGE_PATTERNS = [
        (
            re.compile(
                r"(?:我想学|想学|最近想学|更想学|最想学|偏向学)\s*(java|python|go|golang|rust|c\+\+|typescript|javascript)",
                re.IGNORECASE,
            ),
            "learning_language",
            "学习语言偏好",
        ),
        (
            re.compile(
                r"(?:我喜欢|喜欢|偏好|更喜欢)\s*(java|python|go|golang|rust|c\+\+|typescript|javascript)",
                re.IGNORECASE,
            ),
            "preferred_language",
            "语言偏好",
        ),
    ]

    PROFILE_QUERY_KEYWORDS = ["偏好", "喜欢", "最想学", "想学", "语言", "技术栈", "学习方向"]

    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    def extract_facts(
        self,
        text: str,
        *,
        session_id: str | None = None,
        message_id: str | None = None,
        task_id: str | None = None,
    ) -> list[UserProfileFact]:
        content = text.strip()
        if not content:
            return []

        facts: list[UserProfileFact] = []
        for pattern, category, label in self.LANGUAGE_PATTERNS:
            for match in pattern.finditer(content):
                normalized = self._normalize_language(match.group(1).strip())
                facts.append(
                    UserProfileFact(
                        category=category,
                        label=label,
                        value=normalized,
                        confidence=0.92,
                        source_session_id=session_id,
                        source_message_id=message_id,
                        source_task_id=task_id,
                        summary=f"用户当前表达出对 {normalized} 的稳定偏好。",
                    )
                )
        return self._deduplicate(facts)

    def remember(self, fact: UserProfileFact) -> UserProfileFact:
        fact.value = self._normalize_language(fact.value)
        existing = self.repository.find_user_profile_fact(fact.category, fact.value)
        if existing is not None:
            existing.label = fact.label
            existing.confidence = max(existing.confidence, fact.confidence)
            existing.summary = fact.summary or existing.summary
            existing.status = UserProfileFactStatus.ACTIVE
            existing.superseded_by = None
            existing.source_session_id = fact.source_session_id
            existing.source_message_id = fact.source_message_id
            existing.source_task_id = fact.source_task_id
            return self.repository.save_user_profile_fact(existing)

        saved = self.repository.save_user_profile_fact(fact)
        self._archive_conflicts(saved)
        return saved

    def list_facts(self, limit: int = 50, *, include_inactive: bool = False) -> list[UserProfileFact]:
        return self.repository.list_user_profile_facts(limit=limit, include_inactive=include_inactive)

    def get_fact(self, fact_id: str) -> UserProfileFact | None:
        return self.repository.get_user_profile_fact(fact_id)

    def update_fact(
        self,
        fact_id: str,
        *,
        label: str | None = None,
        value: str | None = None,
        confidence: float | None = None,
        summary: str | None = None,
        status: UserProfileFactStatus | None = None,
    ) -> UserProfileFact | None:
        fact = self.repository.get_user_profile_fact(fact_id)
        if fact is None:
            return None
        if label is not None:
            fact.label = label.strip() or fact.label
        if value is not None:
            fact.value = self._normalize_language(value.strip())
        if confidence is not None:
            fact.confidence = confidence
        if summary is not None:
            fact.summary = summary
        if status is not None:
            fact.status = status
            if status != UserProfileFactStatus.MERGED:
                fact.superseded_by = None
        saved = self.repository.save_user_profile_fact(fact)
        if saved.status == UserProfileFactStatus.ACTIVE:
            self._archive_conflicts(saved)
        return saved

    def merge_fact(self, source_fact_id: str, target_fact_id: str, *, summary: str | None = None) -> UserProfileFact | None:
        source = self.repository.get_user_profile_fact(source_fact_id)
        target = self.repository.get_user_profile_fact(target_fact_id)
        if source is None or target is None:
            return None

        source.status = UserProfileFactStatus.MERGED
        source.superseded_by = target.id
        if summary:
            source.summary = summary
        self.repository.save_user_profile_fact(source)

        target.status = UserProfileFactStatus.ACTIVE
        target.superseded_by = None
        if summary and not target.summary:
            target.summary = summary
        saved = self.repository.save_user_profile_fact(target)
        self._archive_conflicts(saved, skip_ids={source.id, saved.id})
        return saved

    def snapshot(self, limit: int = 8) -> list[str]:
        facts = self.list_facts(limit=limit)
        return [f"{item.label}: {item.value}" for item in facts]

    def match_relevant(self, query: str, limit: int = 5) -> list[UserProfileFact]:
        normalized_query = query.lower()
        facts = self.list_facts(limit=50)
        scored: list[tuple[int, UserProfileFact]] = []
        for fact in facts:
            score = 0
            if fact.value.lower() in normalized_query:
                score += 3
            if any(keyword in query for keyword in self.PROFILE_QUERY_KEYWORDS):
                score += 2
            if fact.category in {"learning_language", "preferred_language"} and any(
                keyword in query for keyword in ["语言", "技术栈", "学习方向", "最想学"]
            ):
                score += 2
            if score > 0:
                scored.append((score, fact))
        scored.sort(key=lambda item: (-item[0], -item[1].updated_at.timestamp()))
        return [item[1] for item in scored[:limit]]

    def _archive_conflicts(self, fact: UserProfileFact, *, skip_ids: set[str] | None = None) -> None:
        skip_ids = skip_ids or set()
        for item in self.repository.list_user_profile_facts_by_category(fact.category, include_inactive=True, limit=100):
            if item.id == fact.id or item.id in skip_ids:
                continue
            if item.status != UserProfileFactStatus.ACTIVE:
                continue
            if item.value == fact.value:
                continue
            item.status = UserProfileFactStatus.ARCHIVED
            item.superseded_by = fact.id
            if not item.summary:
                item.summary = f"该画像已被更新为更近期的偏好：{fact.value}"
            self.repository.save_user_profile_fact(item)

    def _normalize_language(self, value: str) -> str:
        normalized = value.lower()
        mapping = {
            "golang": "Go",
            "go": "Go",
            "java": "Java",
            "python": "Python",
            "rust": "Rust",
            "typescript": "TypeScript",
            "javascript": "JavaScript",
            "c++": "C++",
        }
        return mapping.get(normalized, value)

    def _deduplicate(self, facts: list[UserProfileFact]) -> list[UserProfileFact]:
        unique: dict[tuple[str, str], UserProfileFact] = {}
        for fact in facts:
            unique[(fact.category, fact.value)] = fact
        return list(unique.values())
