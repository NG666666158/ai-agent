"""Citation map for Orion Agent.

Provides a typed extension surface for citation sources and paragraph citations,
enabling future permission and plugin work to build on top of a well-defined
citation model.

Key concepts:
- CitationSource: a single citation with kind, label, detail, and source pointers.
- ParagraphCitation: maps a paragraph index to the sources that informed it.
- source_ids / source_labels: parallel lists linking paragraph text to sources.

Extension points:
- Add new CitationSource.kind values by registering them in this module.
- CitationSource.metadata: reserved dict for plugin-specific annotation.
- CitationSource.source_task_id: enables cross-task citation tracing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from orion_agent.core.models import CitationSource, ParagraphCitation


# Well-known citation kind values used throughout the system.
CITATION_KINDS = {
    "memory": "Long-term memory recall",
    "profile": "User profile fact",
    "session_message": "Chat session message",
    "source_summary": "External material summary",
    "web_search": "Web search result",
    "file": "Local file content",
}


@dataclass
class CitationMap:
    """Accumulates citation sources and paragraph citations for a task.

    This is the primary extension surface for building rich citation graphs.
    Plugins and tools can call add_source() and add_paragraph() to
    register citations that will be included in the task response.
    """

    sources: list[CitationSource] = field(default_factory=list)
    paragraphs: list[ParagraphCitation] = field(default_factory=list)
    _source_index: dict[str, CitationSource] = field(default_factory=dict)

    def add_source(
        self,
        kind: str,
        label: str,
        detail: str,
        *,
        source_record_id: str | None = None,
        source_session_id: str | None = None,
        source_task_id: str | None = None,
        excerpt: str | None = None,
    ) -> str:
        """Register a citation source and return its id.

        Args:
            kind: citation kind (see CITATION_KINDS)
            label: display label for the source
            detail: human-readable detail text
            source_record_id: id of the source record in storage
            source_session_id: session containing the source
            source_task_id: task that produced the source
            excerpt: quoted excerpt relevant to the citation

        Returns:
            The id of the registered CitationSource.
        """
        source = CitationSource(
            kind=kind,
            label=label,
            detail=detail,
            source_record_id=source_record_id,
            source_session_id=source_session_id,
            source_task_id=source_task_id,
            excerpt=excerpt,
        )
        self.sources.append(source)
        self._source_index[source.id] = source
        return source.id

    def add_paragraph(
        self,
        paragraph_index: int,
        paragraph_text: str,
        source_ids: list[str],
        source_labels: list[str],
    ) -> None:
        """Register a paragraph citation mapping.

        Args:
            paragraph_index: zero-based index of the paragraph
            paragraph_text: text of the paragraph
            source_ids: ids of sources that informed this paragraph
            source_labels: parallel list of display labels (same length as source_ids)
        """
        self.paragraphs.append(
            ParagraphCitation(
                paragraph_index=paragraph_index,
                paragraph_text=paragraph_text,
                source_ids=source_ids,
                source_labels=source_labels,
            )
        )

    def get_source(self, source_id: str) -> CitationSource | None:
        """Return a previously registered source by id, or None."""
        return self._source_index.get(source_id)

    def kind_counts(self) -> dict[str, int]:
        """Return a dict of kind -> count for all registered sources."""
        counts: dict[str, int] = {}
        for s in self.sources:
            counts[s.kind] = counts.get(s.kind, 0) + 1
        return counts


def citation_kind_label(kind: str) -> str:
    """Return a human-readable label for a citation kind."""
    return CITATION_KINDS.get(kind, kind)
