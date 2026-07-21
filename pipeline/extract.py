"""
extract.py
----------
Extracts structured text from a textbook PDF.

Produces a list of chunks, each chunk is a piece of body text tagged with
which chapter and section it belongs to. This output feeds into embed.py,
which loads it into the vector database.

Usage:
    python extract.py --pdf "my-book.pdf" --output chunks.json
    python extract.py --pdf "my-book.pdf" --output chunks.json --pages 24 580

Dependencies:
    pip install pdfplumber pandas
"""

import argparse
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass

import pandas as pd
import pdfplumber


# ---------------------------------------------------------------------------
# Data classes
#
# Python dataclasses are like lightweight structs. @dataclass auto-generates
# __init__, __repr__, and other boilerplate based on the fields you declare.
# They make it clear exactly what shape of data each function produces.
# ---------------------------------------------------------------------------


@dataclass
class Node:
    """A chapter or section heading - the structural skeleton of the book."""

    id: int
    type: str        # "chapter" or "section"
    depth: int       # 0 = chapter, 1 = section
    number: str      # e.g. "1" or "" if not detected
    title: str
    page_start: int
    parent_id: int | None


@dataclass
class Chunk:
    """
    A piece of body text, associated with its parent node.
    These are what get embedded and stored in the vector database.
    """

    node_id: int | None   # FK → Node.id (can be None for pre-chapter front matter)
    content: str
    page: int
    order_index: int      # position of this chunk within its parent node


# ---------------------------------------------------------------------------
# Step 1: Extract words from each page
# ---------------------------------------------------------------------------


def extract_words(pdf_path: str, page_start: int, page_end: int) -> pd.DataFrame:
    """
    Opens the PDF and extracts every word with its position metadata.

    pdfplumber's extract_words() gives us each word as a dict with:
      - text:   the word string
      - top:    distance from the top of the page (in PDF points)
      - x0:     left edge of the word bounding box
      - height: rendered font height

    We use `with` so the file handle is always closed, even if an exception
    occurs mid-loop. This is a Python best practice for any resource that
    needs to be explicitly released (files, DB connections, network sockets).
    """
    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[page_start:page_end]

        for page_num, page in enumerate(pages, start=page_start):
            page_height = page.height  # total height of this page in points

            for word in page.extract_words():
                rows.append({
                    "page": page_num,
                    "top": round(word["top"]),
                    "x0": word["x0"],
                    "height": round(word["height"], 1),
                    "text": word["text"],
                    # Store relative vertical position (0.0 = top, 1.0 = bottom).
                    # We use this later to filter headers and footers by position
                    # rather than by font size, which is more reliable.
                    "top_pct": word["top"] / page_height if page_height else 0,
                })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 2: Group words into lines
# ---------------------------------------------------------------------------


def build_lines(df: pd.DataFrame) -> pd.DataFrame:
    """
    Words on the same page at the same vertical position (top) belong to the
    same line. We group them and join their text with spaces.

    groupby(['page', 'top']) creates one group per unique (page, top) pair.
    agg() then collapses each group: take the first height value, join all text.

    We also record the minimum x0 (leftmost word) — this helps detect
    indented text and code blocks later.
    """
    lines = df.groupby(["page", "top"]).agg(
        height=("height", "first"),
        text=("text", " ".join),
        top_pct=("top_pct", "first"),
        x0=("x0", "min"),
    ).reset_index()

    return lines.sort_values(["page", "top"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 3: Classify each line as chapter heading, section heading, or body
# ---------------------------------------------------------------------------


def classify_lines(lines_df: pd.DataFrame) -> pd.DataFrame:
    """
    Determines the structural role of each line based on font size.

    The most common font height in the document is assumed to be body text.
    Headings are larger, we use multiples of the body size as thresholds.

    We only merge lines that are *adjacent* (consecutive in the sorted
    DataFrame) — which handles multi-line headings without destroying paragraphs.
    """
    # Find the modal (most common) font height — this is body text size.
    # Counter.most_common(1) returns [(value, count)] — we unpack the value.
    body_height = Counter(lines_df["height"]).most_common(1)[0][0]

    # Headings are proportionally larger than body text.
    # These multipliers are tuned for DDIA's PDF layout.
    section_threshold = body_height * 1.3
    chapter_threshold = body_height * 1.8

    def classify(h: float) -> str:
        if h >= chapter_threshold:
            return "chapter"
        elif h >= section_threshold:
            return "section"
        else:
            return "body"

    lines_df = lines_df.copy()
    lines_df["type"] = lines_df["height"].apply(classify)

    # Merge adjacent lines that have the same height AND type on the same page.
    # This handles multi-line chapter titles ("Reliable, Scalable,\nand Maintainable")
    # without accidentally joining unrelated body text.
    #
    # BUG FIX: original merged ALL same-height lines on a page into one.
    # Now we check adjacency: line i merges into i-1 only if they're consecutive.
    merged = []
    for _, row in lines_df.iterrows():
        row_dict = row.to_dict()
        if (
            merged
            and merged[-1]["page"] == row_dict["page"]
            and merged[-1]["type"] == row_dict["type"]
            and merged[-1]["type"] != "body"   # never merge body lines
            and abs(merged[-1]["height"] - row_dict["height"]) < 0.5
        ):
            merged[-1]["text"] += " " + row_dict["text"]
        else:
            merged.append(row_dict)

    return pd.DataFrame(merged)


# ---------------------------------------------------------------------------
# Step 4: Filter headers, footers, and other noise
# ---------------------------------------------------------------------------


def filter_noise(lines_df: pd.DataFrame) -> pd.DataFrame:
    """
    Removes page numbers, running headers, and footers.

    Filtering strategy (all general, not book-specific):
      1. Position — anything in the top/bottom 7% of the page is header/footer.
      2. Pure numbers — standalone page numbers like "42".
      3. Running headers — a line that is just "<text> | <number>" or
         "<number> | <text>". This is the classic book running-header format
         (section title on one side, page number on the other) and is noise
         regardless of which book it is.
      4. Roman-numeral footnote markers like "ii. ".
    """
    # 1. Position-based: remove content very close to the page edges
    positional_noise = (lines_df["top_pct"] < 0.07) | (lines_df["top_pct"] > 0.93)

    # 2. Pure numbers are almost certainly page numbers
    numeric_noise = lines_df["text"].str.strip().str.match(r"^\d+$")

    # 3. Running headers in EITHER direction, as a standalone line:
    #    "Problems with Replication Lag | 163"  (text | number)
    #    "163 | Chapter 5. Replication"          (number | text)
    running_header_noise = lines_df["text"].str.strip().str.match(
        r"^(.+\s*\|\s*\d+|\d+\s*\|\s*.+)$"
    )

    # 4. Roman-numeral footnote markers like "ii. ..."
    footnote_noise = lines_df["text"].str.match(r"^[ivxlcdm]+\.\s", re.IGNORECASE)

    keep = ~(positional_noise | numeric_noise | running_header_noise | footnote_noise)
    filtered = lines_df[keep].reset_index(drop=True)

    removed_count = len(lines_df) - len(filtered)
    print(f"  Filtered {removed_count} noise lines (headers, footers, page numbers)")

    return filtered

# ---------------------------------------------------------------------------
# Step 5: Merge consecutive body lines into paragraphs
# ---------------------------------------------------------------------------

def merge_paragraphs(lines_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merges consecutive body lines into paragraphs.

    A new paragraph starts when:
      - the line type changes (body -> heading etc.), or
      - we move to a different page, or
      - there's a vertical gap larger than a normal line spacing
        (a blank line, signalling a paragraph break).

    BUG FIX: we compare each line against the PREVIOUS line's top
    (tracked via last_top), not the paragraph's first line. Comparing
    against the first line made the gap grow as the paragraph grew,
    causing paragraphs to split after a few lines.
    """
    merged = []
    last_top = None  # top of the immediately preceding line

    for _, row in lines_df.iterrows():
        r = row.to_dict()

        if r["type"] != "body":
            merged.append(r)
            last_top = None
            continue

        if (
            merged
            and merged[-1]["type"] == "body"
            and merged[-1]["page"] == r["page"]
            and last_top is not None
            and (r["top"] - last_top) < r["height"] * 1.8   # normal line spacing
        ):
            merged[-1]["text"] += " " + r["text"]
        else:
            merged.append(r)

        last_top = r["top"]

    return pd.DataFrame(merged)

# ---------------------------------------------------------------------------
# Step 6: Build nodes (structure) and chunks (content)
# ---------------------------------------------------------------------------


def build_nodes_and_chunks(
    lines_df: pd.DataFrame,
) -> tuple[list[Node], list[Chunk]]:
    """
    Walks through the classified lines and builds two lists:
      - nodes:  the structural skeleton (chapters and sections)
      - chunks: the actual text content, each linked to its parent node

    The logic works like a state machine: as we scan lines top-to-bottom,
    we track the "current chapter" and "current section". When we hit a
    chapter heading, we update current_chapter. When we hit a section heading,
    we update current_section (and reset it when a new chapter starts).
    Body text gets attached to whatever the current state is.
    """
    nodes: list[Node] = []
    chunks: list[Chunk] = []

    # State
    current_chapter_id: int | None = None
    current_section_id: int | None = None
    chunk_order = 0
    node_id = 0
    chapter_number: str | None = None

    # BUG FIX: create a "front matter" node to catch any text before Chapter 1.
    # Without this, early text (preface, TOC) silently gets node_id=None.
    node_id += 1
    front_matter_id = node_id
    nodes.append(Node(
        id=node_id,
        type="front_matter",
        depth=0,
        number="0",
        title="Front Matter",
        page_start=0,
        parent_id=None,
    ))
    current_chapter_id = front_matter_id

    for _, row in lines_df.iterrows():
        text = row["text"].strip()

        # Detect the "CHAPTER X" label line — DDIA prints this on its own line
        # before the actual chapter title. We capture the number and skip the line
        # itself (it's not a real heading, just a label).
        chapter_label = re.match(r"^CHAPTER\s+(\d+)$", text, re.IGNORECASE)
        if chapter_label:
            chapter_number = chapter_label.group(1)
            continue

        if row["type"] == "chapter":
            node_id += 1
            current_chapter_id = node_id
            current_section_id = None  # sections reset when a new chapter starts
            chunk_order = 0
            nodes.append(Node(
                id=node_id,
                type="chapter",
                depth=0,
                number=chapter_number or "",
                title=text,
                page_start=int(row["page"]),
                parent_id=None,
            ))
            chapter_number = None  # consumed — reset for next chapter

        elif row["type"] == "section":
            node_id += 1
            current_section_id = node_id
            chunk_order = 0
            nodes.append(Node(
                id=node_id,
                type="section",
                depth=1,
                number="",
                title=text,
                page_start=int(row["page"]),
                parent_id=current_chapter_id,
            ))

        else:
            # Body text — skip very short lines (likely artefacts)
            if len(text) < 10:
                continue

            chunk_order += 1
            chunks.append(Chunk(
                # Prefer the current section as parent; fall back to chapter.
                # current_chapter_id is never None here because we pre-seed it
                # with front_matter_id above.
                node_id=current_section_id or current_chapter_id,
                content=text,
                page=int(row["page"]),
                order_index=chunk_order,
            ))

    return nodes, chunks


# ---------------------------------------------------------------------------
# Step 7: Save output to JSON
# ---------------------------------------------------------------------------

def save_output(
    nodes: list[Node],
    chunks: list[Chunk],
    output_path: str,
) -> None:
    """
    Writes nodes and chunks to a JSON file.

    asdict() converts a dataclass instance into a plain dict, which json.dump
    can serialise. We do this for every item in both lists.
    """
    output = {
        "nodes": [asdict(n) for n in nodes],
        "chunks": [asdict(c) for c in chunks],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(nodes)} nodes and {len(chunks)} chunks → {output_path}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def process(pdf_path: str, output_path: str, page_start: int, page_end: int) -> None:
    print(f"Processing: {pdf_path} (pages {page_start}–{page_end})")

    print("  Extracting words...")
    df = extract_words(pdf_path, page_start, page_end)
    print(f"  {len(df)} words extracted")

    print("  Building lines...")
    lines = build_lines(df)
    print(f"  {len(lines)} lines")

    print("  Classifying lines...")
    classified = classify_lines(lines)

    print("  Filtering noise...")
    clean = filter_noise(classified)

    print("  Merging paragraphs...")
    merged = merge_paragraphs(clean)

    print("  Building nodes and chunks...")
    nodes, chunks = build_nodes_and_chunks(merged)

    chapter_nodes = [n for n in nodes if n.type == "chapter"]
    print(f"\n  Found {len(chapter_nodes)} chapters:")
    for node in chapter_nodes:
        node_chunks = [c for c in chunks if c.node_id == node.id]
        print(f"    Ch.{node.number or '?'} {node.title[:55]!r} — {node_chunks} chunks direct")

    save_output(nodes, chunks, output_path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract and structure text from a textbook PDF."
    )
    parser.add_argument("--pdf", required=True, help="Path to the PDF file")
    parser.add_argument("--output", default="chunks.json", help="Output JSON path")
    parser.add_argument("--pages", nargs=2, type=int, default=None,
                        metavar=("START", "END"),
                        help="Page range to process (0-indexed). Omit to process all.")

    args = parser.parse_args()

    page_start = 0
    page_end = None

    if args.pages:
        page_start, page_end = args.pages

    process(args.pdf, args.output, page_start, page_end)


if __name__ == "__main__":
    main()
