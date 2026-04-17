import unittest

from orion_agent.core.citation_map import (
    CITATION_KINDS,
    CitationMap,
    citation_kind_label,
)


class CitationMapTests(unittest.TestCase):
    def test_add_source_returns_source_id(self) -> None:
        # 场景：add_source 返回注册的 citation source id。
        cmap = CitationMap()
        source_id = cmap.add_source(
            kind="memory",
            label="用户偏好",
            detail="用户偏好中文回答",
            source_record_id="fact_123",
        )
        self.assertIsInstance(source_id, str)
        self.assertEqual(len(cmap.sources), 1)
        self.assertEqual(cmap.sources[0].kind, "memory")
        self.assertEqual(cmap.sources[0].label, "用户偏好")

    def test_add_paragraph_records_citation(self) -> None:
        # 场景：add_paragraph 正确记录段落引用映射。
        cmap = CitationMap()
        source_id = cmap.add_source(
            kind="memory", label="记忆", detail="用户偏好中文"
        )
        cmap.add_paragraph(
            paragraph_index=0,
            paragraph_text="用户希望用中文回答。",
            source_ids=[source_id],
            source_labels=["记忆"],
        )
        self.assertEqual(len(cmap.paragraphs), 1)
        self.assertEqual(cmap.paragraphs[0].paragraph_index, 0)
        self.assertEqual(cmap.paragraphs[0].source_ids, [source_id])

    def test_get_source_returns_registered_source(self) -> None:
        # 场景：get_source 返回之前注册的 source。
        cmap = CitationMap()
        source_id = cmap.add_source(
            kind="profile", label="画像", detail="语言偏好"
        )
        result = cmap.get_source(source_id)
        self.assertIsNotNone(result)
        self.assertEqual(result.kind, "profile")

    def test_get_source_returns_none_for_unknown_id(self) -> None:
        # 场景：get_source 对未知 id 返回 None。
        cmap = CitationMap()
        self.assertIsNone(cmap.get_source("unknown_id"))

    def test_kind_counts_returns_correct_counts(self) -> None:
        # 场景：kind_counts 返回各 kind 的正确数量。
        cmap = CitationMap()
        cmap.add_source(kind="memory", label="L1", detail="D1")
        cmap.add_source(kind="memory", label="L2", detail="D2")
        cmap.add_source(kind="profile", label="L3", detail="D3")
        counts = cmap.kind_counts()
        self.assertEqual(counts["memory"], 2)
        self.assertEqual(counts["profile"], 1)

    def test_citation_kind_label_returns_known_label(self) -> None:
        # 场景：citation_kind_label 对已知 kind 返回对应标签。
        self.assertEqual(citation_kind_label("memory"), "Long-term memory recall")
        self.assertEqual(citation_kind_label("profile"), "User profile fact")
        self.assertEqual(citation_kind_label("web_search"), "Web search result")

    def test_citation_kind_label_returns_kind_for_unknown(self) -> None:
        # 场景：citation_kind_label 对未知 kind 返回 kind 本身。
        self.assertEqual(citation_kind_label("unknown_kind"), "unknown_kind")

    def test_citation_kinds_covers_standard_kinds(self) -> None:
        # 场景：CITATION_KINDS 覆盖所有标准引用类型。
        standard_kinds = ["memory", "profile", "session_message", "source_summary", "web_search", "file"]
        for kind in standard_kinds:
            self.assertIn(kind, CITATION_KINDS, f"kind '{kind}' should be in CITATION_KINDS")


if __name__ == "__main__":
    unittest.main()