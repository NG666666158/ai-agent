from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from enum import Enum

from orion_agent.core.models import ProfileFactCleanupReport, UserProfileFact, UserProfileFactStatus, utcnow
from orion_agent.core.repository import TaskRepository


class PreferenceCategory(str, Enum):
    LEARNING_LANGUAGE = "learning_language"
    PREFERRED_LANGUAGE = "preferred_language"
    FRAMEWORK = "framework"
    DOMAIN = "domain"
    OUTPUT_FORMAT = "output_format"
    TONE = "tone"


class UserProfileManager:
    """Stores stable user preferences and retrieves relevant profile facts."""

    # Confidence decay: half-life in days
    CONFIDENCE_HALF_LIFE_DAYS = 30.0
    # Minimum effective confidence floor
    MIN_EFFECTIVE_CONFIDENCE = 0.1

    LANGUAGE_PATTERNS = [
        (
            re.compile(
                r"(?:我想学|想学|最近想学|更想学|最想学|偏向学)\s*(java|python|go|golang|rust|c\+\+|typescript|javascript)",
                re.IGNORECASE,
            ),
            PreferenceCategory.LEARNING_LANGUAGE,
            "学习语言偏好",
        ),
        (
            re.compile(
                r"(?:我喜欢|喜欢|偏好|更喜欢)\s*(java|python|go|golang|rust|c\+\+|typescript|javascript)",
                re.IGNORECASE,
            ),
            PreferenceCategory.PREFERRED_LANGUAGE,
            "语言偏好",
        ),
    ]

    FRAMEWORK_PATTERNS = [
        (
            re.compile(
                r"(?:我喜欢|偏好|更偏好|使用|习惯用|熟悉)\s*(react|vue|angular|next\.?js|fastapi|flask|django|spring|nextjs)",
                re.IGNORECASE,
            ),
            PreferenceCategory.FRAMEWORK,
            "框架偏好",
        ),
    ]

    DOMAIN_PATTERNS = [
        (
            re.compile(
                r"(?:我主要做|主要做|工作领域|行业|业务领域)\s*(前端|后端|全栈|移动端|嵌入式|数据|机器学习|devops|云原生|区块链|游戏)",
                re.IGNORECASE,
            ),
            PreferenceCategory.DOMAIN,
            "工作领域",
        ),
        (
            re.compile(
                r"(?:关注|感兴趣|想深入)\s*(前端|后端|全栈|移动端|嵌入式|数据|机器学习|devops|云原生|区块链|游戏)",
                re.IGNORECASE,
            ),
            PreferenceCategory.DOMAIN,
            "兴趣领域",
        ),
    ]

    OUTPUT_FORMAT_PATTERNS = [
        (
            re.compile(
                r"(?:喜欢|偏好|想要)\s*(markdown|表格|列表|代码|图表|mermaid|json|xml|纯文本)",
                re.IGNORECASE,
            ),
            PreferenceCategory.OUTPUT_FORMAT,
            "输出格式偏好",
        ),
        (
            re.compile(
                r"(?:结果?用|输出格式|写成)\s*(markdown|表格|列表|代码|图表|mermaid|json|xml|纯文本)",
                re.IGNORECASE,
            ),
            PreferenceCategory.OUTPUT_FORMAT,
            "输出格式偏好",
        ),
    ]

    TONE_PATTERNS = [
        (
            re.compile(
                r"(?:语气|风格|口吻|说话方式)\s*(简洁|详细|正式|轻松|技术|友好|严谨)",
                re.IGNORECASE,
            ),
            PreferenceCategory.TONE,
            "交流风格偏好",
        ),
        (
            re.compile(
                r"(?:请|能不能|可以)\s*(简洁|详细|正式|轻松|技术|友好|严谨)\s*(说|讲|回答|解释|写)",
                re.IGNORECASE,
            ),
            PreferenceCategory.TONE,
            "交流风格偏好",
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
        all_pattern_groups = [
            (self.LANGUAGE_PATTERNS, self._normalize_language),
            (self.FRAMEWORK_PATTERNS, self._normalize_framework),
            (self.DOMAIN_PATTERNS, self._normalize_domain),
            (self.OUTPUT_FORMAT_PATTERNS, self._normalize_output_format),
            (self.TONE_PATTERNS, lambda v: v.strip()),
        ]

        for pattern_group, normalizer in all_pattern_groups:
            for pattern, category, label in pattern_group:
                for match in pattern.finditer(content):
                    normalized = normalizer(match.group(1).strip())
                    facts.append(
                        UserProfileFact(
                            category=category.value,
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

    def effective_confidence(self, fact: UserProfileFact) -> float:
        """Compute time-decayed effective confidence.

        Returns raw confidence for ACTIVE facts, applying exponential decay
        based on time since last update. ARCHIVED/MERGED facts return the floor.
        """
        if fact.status != UserProfileFactStatus.ACTIVE:
            return self.MIN_EFFECTIVE_CONFIDENCE
        now = utcnow()
        age_delta = now - fact.updated_at
        age_days = age_delta.total_seconds() / 86400.0
        decay_factor = 0.5 ** (age_days / self.CONFIDENCE_HALF_LIFE_DAYS)
        return max(fact.confidence * decay_factor, self.MIN_EFFECTIVE_CONFIDENCE)

    def remember(self, fact: UserProfileFact) -> UserProfileFact:
        """Store a profile fact, preserving prior history instead of blind overwrite.

        When a matching fact exists (same category + value), archive it and
        store the new one as a fresh record with its own timeline entry.
        """
        existing = self.repository.find_user_profile_fact(fact.category, fact.value)
        if existing is not None:
            # Archive the old record so history remains traceable
            existing.status = UserProfileFactStatus.ARCHIVED
            existing.superseded_by = None  # preserved for timeline; history is readable via prior records
            self.repository.save_user_profile_fact(existing)

        saved = self.repository.save_user_profile_fact(fact)
        self._archive_conflicts(saved)
        return saved

    def list_facts(self, limit: int = 50, *, include_inactive: bool = False) -> list[UserProfileFact]:
        return self.repository.list_user_profile_facts(limit=limit, include_inactive=include_inactive)

    def cleanup_policy_report(self, *, staleness_threshold: float = 0.7) -> ProfileFactCleanupReport:
        all_facts = self.repository.list_user_profile_facts(limit=500, include_inactive=False)
        entries: list[str] = []
        archived_count = 0

        for fact in all_facts:
            effective = self.effective_confidence(fact)
            if effective < staleness_threshold:
                entries.append(fact.id)
                fact.status = UserProfileFactStatus.ARCHIVED
                self.repository.save_user_profile_fact(fact)
                archived_count += 1

        return ProfileFactCleanupReport(
            evaluated_count=len(all_facts),
            archived_count=archived_count,
            merged_count=0,
            staleness_threshold=staleness_threshold,
            entries=entries,
        )

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
            fact.value = self._normalize(value.strip(), fact.category)
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
        scored: list[tuple[float, UserProfileFact]] = []
        for fact in facts:
            score = 0
            if fact.value.lower() in normalized_query:
                score += 3
            if any(keyword in query for keyword in self.PROFILE_QUERY_KEYWORDS):
                score += 2
            if fact.category in {
                PreferenceCategory.LEARNING_LANGUAGE.value,
                PreferenceCategory.PREFERRED_LANGUAGE.value,
            } and any(keyword in query for keyword in ["语言", "技术栈", "学习方向", "最想学"]):
                score += 2
            if score > 0:
                # Weight by effective (time-decayed) confidence
                effective = self.effective_confidence(fact)
                scored.append((score * effective, fact))
        scored.sort(key=lambda item: (-item[0], -item[1].updated_at.timestamp()))
        results = [item[1] for item in scored[:limit]]
        # Track governance access metadata and persist
        now = utcnow()
        for fact in results:
            fact.last_accessed_at = now
            fact.accessed_count += 1
            self.repository.save_user_profile_fact(fact)
        return results

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
                item.summary = f"该画像已被更新为更新近的偏好：{fact.value}"
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

    def _normalize_framework(self, value: str) -> str:
        normalized = value.lower()
        mapping = {
            "next.js": "Next.js",
            "nextjs": "Next.js",
            "vue": "Vue",
            "react": "React",
            "angular": "Angular",
            "fastapi": "FastAPI",
            "flask": "Flask",
            "django": "Django",
            "spring": "Spring",
        }
        return mapping.get(normalized, value.title())

    def _normalize_domain(self, value: str) -> str:
        return value.strip()

    def _normalize_output_format(self, value: str) -> str:
        normalized = value.lower()
        mapping = {
            "markdown": "Markdown",
            "mermaid": "Mermaid 图",
            "json": "JSON",
            "xml": "XML",
            "表格": "表格",
            "列表": "列表",
            "代码": "代码块",
            "图表": "图表",
            "纯文本": "纯文本",
        }
        return mapping.get(normalized, value)

    def _normalize(self, value: str, category: str) -> str:
        if category in {PreferenceCategory.LEARNING_LANGUAGE.value, PreferenceCategory.PREFERRED_LANGUAGE.value}:
            return self._normalize_language(value)
        if category == PreferenceCategory.FRAMEWORK.value:
            return self._normalize_framework(value)
        if category == PreferenceCategory.DOMAIN.value:
            return self._normalize_domain(value)
        if category == PreferenceCategory.OUTPUT_FORMAT.value:
            return self._normalize_output_format(value)
        return value.strip()

    def _deduplicate(self, facts: list[UserProfileFact]) -> list[UserProfileFact]:
        unique: dict[tuple[str, str], UserProfileFact] = {}
        for fact in facts:
            unique[(fact.category, fact.value)] = fact
        return list(unique.values())
