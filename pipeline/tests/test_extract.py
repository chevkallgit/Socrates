"""
tests/test_extract.py
---------------------
Unit tests for the extraction pipeline.

We test the logic functions directly using synthetic data — no PDF file needed.
This is an important principle: pure functions (input → output, no side effects)
are easy to test. We isolate them from the filesystem by constructing DataFrames
directly in the test.

Run with:
    pytest tests/ -v
"""

import pandas as pd
import pytest

from extract import (
    build_lines,
    build_nodes_and_chunks,
    classify_lines,
    filter_noise,
)


# ---------------------------------------------------------------------------
# Helpers — build synthetic DataFrames that mimic pdfplumber output
# ---------------------------------------------------------------------------


def make_words_df(rows: list[dict]) -> pd.DataFrame:
    """Create a minimal word DataFrame for testing."""
    return pd.DataFrame(rows)


def make_lines_df(rows: list[dict]) -> pd.DataFrame:
    """Create a classified lines DataFrame for testing."""
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# build_lines
# ---------------------------------------------------------------------------


class TestBuildLines:
    def test_groups_words_on_same_line(self):
        """Words at the same (page, top) should be joined into one line."""
        df = make_words_df([
            {"page": 0, "top": 100, "x0": 10,  "height": 12.0, "text": "Hello", "top_pct": 0.2},
            {"page": 0, "top": 100, "x0": 50,  "height": 12.0, "text": "World", "top_pct": 0.2},
            {"page": 0, "top": 120, "x0": 10,  "height": 12.0, "text": "Next",  "top_pct": 0.3},
        ])
        lines = build_lines(df)

        assert len(lines) == 2
        assert lines.iloc[0]["text"] == "Hello World"
        assert lines.iloc[1]["text"] == "Next"

    def test_different_pages_not_merged(self):
        """Same top value on different pages should produce separate lines."""
        df = make_words_df([
            {"page": 0, "top": 100, "x0": 10, "height": 12.0, "text": "Page0", "top_pct": 0.2},
            {"page": 1, "top": 100, "x0": 10, "height": 12.0, "text": "Page1", "top_pct": 0.2},
        ])
        lines = build_lines(df)
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# classify_lines
# ---------------------------------------------------------------------------


class TestClassifyLines:
    def _make_input(self, heights: list[float]) -> pd.DataFrame:
        """Build a minimal lines DataFrame with the given heights."""
        rows = [
            {
                "page": 0,
                "top": i * 20,
                "height": h,
                "text": f"Line {i}",
                "top_pct": 0.1 + i * 0.05,
                "x0": 50.0,
            }
            for i, h in enumerate(heights)
        ]
        return pd.DataFrame(rows)

    def test_body_is_modal_height(self):
        """The most common height should be classified as body."""
        # 5 lines at 12.0 (body), 1 at 22.0 (chapter)
        df = self._make_input([12.0, 12.0, 12.0, 12.0, 12.0, 22.0])
        result = classify_lines(df)
        body_rows = result[result["type"] == "body"]
        assert len(body_rows) == 5

    def test_chapter_heading_detected(self):
        """Heights >= 1.8x body should be classified as chapter."""
        df = self._make_input([12.0, 12.0, 12.0, 12.0, 12.0, 22.0])
        result = classify_lines(df)
        chapter_rows = result[result["type"] == "chapter"]
        assert len(chapter_rows) == 1

    def test_section_heading_detected(self):
        """Heights between 1.3x and 1.8x body should be classified as section."""
        df = self._make_input([12.0, 12.0, 12.0, 12.0, 16.0])
        result = classify_lines(df)
        section_rows = result[result["type"] == "section"]
        assert len(section_rows) == 1

    def test_adjacent_headings_merged(self):
        """Two adjacent chapter-height lines should be merged into one."""
        # Chapter title that spans two lines in the PDF
        df = self._make_input([12.0, 12.0, 12.0, 22.0, 22.0])
        result = classify_lines(df)
        chapter_rows = result[result["type"] == "chapter"]
        # Should be merged into one chapter heading, not two
        assert len(chapter_rows) == 1
        assert "Line 3" in chapter_rows.iloc[0]["text"]
        assert "Line 4" in chapter_rows.iloc[0]["text"]

    def test_body_lines_not_merged(self):
        """Adjacent body lines should NOT be merged together."""
        df = self._make_input([12.0, 12.0, 12.0])
        result = classify_lines(df)
        body_rows = result[result["type"] == "body"]
        # All three should remain separate
        assert len(body_rows) == 3


# ---------------------------------------------------------------------------
# filter_noise
# ---------------------------------------------------------------------------


class TestFilterNoise:
    def _make_lines(self, rows: list[dict]) -> pd.DataFrame:
        defaults = {"height": 12.0, "x0": 50.0, "type": "body", "page": 0, "top": 100}
        return pd.DataFrame([{**defaults, **r} for r in rows])

    def test_removes_page_numbers(self):
        """Purely numeric lines should be filtered out."""
        df = self._make_lines([
            {"text": "42", "top_pct": 0.5},
            {"text": "Real content here", "top_pct": 0.5},
        ])
        result = filter_noise(df)
        assert len(result) == 1
        assert result.iloc[0]["text"] == "Real content here"

    def test_removes_footer_by_position(self):
        """Lines in the bottom 7% of the page should be filtered."""
        df = self._make_lines([
            {"text": "Some footer text", "top_pct": 0.96},
            {"text": "Body text", "top_pct": 0.5},
        ])
        result = filter_noise(df)
        assert len(result) == 1

    def test_removes_header_by_position(self):
        """Lines in the top 7% of the page should be filtered."""
        df = self._make_lines([
            {"text": "Running header", "top_pct": 0.03},
            {"text": "Body text", "top_pct": 0.5},
        ])
        result = filter_noise(df)
        assert len(result) == 1

    def test_keeps_mid_page_content(self):
        """Normal mid-page content should pass through unchanged."""
        df = self._make_lines([
            {"text": "This is a normal paragraph.", "top_pct": 0.4},
            {"text": "And another sentence here.", "top_pct": 0.6},
        ])
        result = filter_noise(df)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# build_nodes_and_chunks
# ---------------------------------------------------------------------------


class TestBuildNodesAndChunks:
    def _make_classified(self, rows: list[dict]) -> pd.DataFrame:
        """Build a classified lines DataFrame for node/chunk building."""
        defaults = {"height": 12.0, "x0": 50.0}
        return pd.DataFrame([{**defaults, **r} for r in rows])

    def test_chapter_creates_node(self):
        df = self._make_classified([
            {"page": 5, "top": 10, "type": "chapter", "text": "Reliable Systems"},
            {"page": 5, "top": 30, "type": "body",    "text": "Reliability means the system continues to work correctly."},
        ])
        nodes, chunks = build_nodes_and_chunks(df)
        chapter_nodes = [n for n in nodes if n.type == "chapter"]
        assert len(chapter_nodes) == 1
        assert chapter_nodes[0].title == "Reliable Systems"

    def test_body_text_creates_chunk(self):
        df = self._make_classified([
            {"page": 5, "top": 10, "type": "chapter", "text": "Reliability"},
            {"page": 5, "top": 30, "type": "body",    "text": "Reliability means the system continues to work correctly."},
        ])
        nodes, chunks = build_nodes_and_chunks(df)
        assert len(chunks) == 1
        assert chunks[0].content == "Reliability means the system continues to work correctly."

    def test_orphaned_text_goes_to_front_matter(self):
        """Text before any chapter heading should not produce null node_ids."""
        df = self._make_classified([
            {"page": 0, "top": 10, "type": "body", "text": "Preface text before any chapter."},
        ])
        nodes, chunks = build_nodes_and_chunks(df)
        # Should have a front matter node
        front_matter = [n for n in nodes if n.type == "front_matter"]
        assert len(front_matter) == 1
        # Chunk should be assigned to it, not have node_id=None
        assert chunks[0].node_id is not None
        assert chunks[0].node_id == front_matter[0].id

    def test_section_inherits_parent_chapter(self):
        """A section node should have parent_id pointing to its chapter."""
        df = self._make_classified([
            {"page": 5, "top": 10, "type": "chapter", "text": "Data Models"},
            {"page": 5, "top": 30, "type": "section", "text": "Relational Model"},
        ])
        nodes, chunks = build_nodes_and_chunks(df)
        chapter = next(n for n in nodes if n.type == "chapter")
        section = next(n for n in nodes if n.type == "section")
        assert section.parent_id == chapter.id

    def test_chapter_number_extracted_from_label(self):
        """A 'CHAPTER X' label line before the title should set the number."""
        df = self._make_classified([
            {"page": 5, "top": 10, "type": "chapter", "text": "CHAPTER 1"},
            {"page": 5, "top": 20, "type": "chapter", "text": "Reliable Systems"},
        ])
        nodes, chunks = build_nodes_and_chunks(df)
        chapter_nodes = [n for n in nodes if n.type == "chapter"]
        assert chapter_nodes[0].number == "1"

    def test_section_resets_on_new_chapter(self):
        """Body text after a new chapter should not attach to the previous section."""
        df = self._make_classified([
            {"page": 1, "top": 10, "type": "chapter", "text": "Chapter One"},
            {"page": 1, "top": 20, "type": "section", "text": "Section A"},
            {"page": 2, "top": 10, "type": "chapter", "text": "Chapter Two"},
            {"page": 2, "top": 20, "type": "body",    "text": "Body text in chapter two with no section."},
        ])
        nodes, chunks = build_nodes_and_chunks(df)
        chapter_two = next(n for n in nodes if n.title == "Chapter Two")
        body_chunk = chunks[-1]
        # Chunk should attach to chapter two, not the section from chapter one
        assert body_chunk.node_id == chapter_two.id
