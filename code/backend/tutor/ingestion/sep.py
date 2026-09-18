"""
SEP HTML parsing and chunking.

Parses Stanford Encyclopedia of Philosophy HTML files, strips boilerplate,
walks the heading hierarchy, and splits section text into ≤500-token chunks.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import tiktoken
from bs4 import BeautifulSoup, NavigableString, Tag

_enc = tiktoken.get_encoding("cl100k_base")
_MAX_TOKENS = 500


def _count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def _clean_text(text: str) -> str:
    """Collapse whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def _strip_boilerplate(soup: BeautifulSoup) -> None:
    """Remove navigation, sidebar, bibliography and footer sections in-place."""
    # IDs to remove entirely
    remove_ids = [
        "toc",
        "bibliography",
        "academic-tools",
        "other-internet-resources",
        "related-entries",
        "footer",
        "navigation",
        "sidebar",
        "header",
        "header-wrapper",
        "site-footer",
    ]
    for id_ in remove_ids:
        el = soup.find(id=id_)
        if el:
            el.decompose()

    # Also remove by common class patterns
    for cls in ("sidebar", "footer", "nav", "toc", "bibliography"):
        for el in soup.find_all(class_=re.compile(cls, re.I)):
            el.decompose()

    # Remove <script> and <style> tags
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()


def _get_paragraph_texts(section_el) -> list[str]:
    """Return non-empty paragraph text strings from a container element."""
    paragraphs = []
    for p in section_el.find_all("p", recursive=True):
        text = _clean_text(p.get_text())
        if text:
            paragraphs.append(text)
    return paragraphs


def _split_paragraphs(paragraphs: list[str], max_tokens: int = _MAX_TOKENS) -> list[str]:
    """
    Pack paragraphs greedily into chunks of ≤ max_tokens.
    A single paragraph that exceeds max_tokens becomes its own chunk.
    """
    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = _count_tokens(para)
        if current_tokens + para_tokens > max_tokens and current_parts:
            chunks.append(" ".join(current_parts))
            current_parts = []
            current_tokens = 0
        current_parts.append(para)
        current_tokens += para_tokens

    if current_parts:
        chunks.append(" ".join(current_parts))

    return chunks


def chunk_sep_file(html_path: Path, manifest_entry: dict) -> list[dict]:
    """
    Parse one SEP HTML file and return a list of chunk dicts.

    Each chunk:
        {
            "text": str,
            "metadata": {
                "source_id": str,
                "source_type": "sep",
                "title": str,
                "url": str,
                "section": str,
                "subsection": str,
                "chunk_index": int,
            }
        }
    """
    source_id: str = manifest_entry["id"]
    title: str = manifest_entry["title"]
    url: str = manifest_entry["url"]

    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    _strip_boilerplate(soup)

    # Target the main article body
    main = soup.find(id="main-text") or soup.find("div", class_="entry-content") or soup.body
    if main is None:
        return []

    chunks: list[dict] = []
    chunk_index = 0

    def make_chunk(text: str, section: str, subsection: str) -> dict:
        nonlocal chunk_index
        record = {
            "text": text,
            "metadata": {
                "source_id": source_id,
                "source_type": "sep",
                "title": title,
                "url": url,
                "section": section,
                "subsection": subsection,
                "chunk_index": chunk_index,
            },
        }
        chunk_index += 1
        return record

    # h2 section headings whose entire content should be skipped
    _BLOCKED_SECTIONS = {
        "a note on texts and references",
    }

    # Walk top-level children of main, tracking current h2/h3 context.
    # We accumulate paragraphs per leaf section, then chunk them.
    current_h2 = ""
    current_h3 = ""
    skip_section = False  # True while inside a blocked h2 section
    pending_paragraphs: list[str] = []

    def flush(section: str, subsection: str) -> None:
        if not pending_paragraphs:
            return
        combined = " ".join(pending_paragraphs)
        if _count_tokens(combined) <= _MAX_TOKENS:
            chunks.append(make_chunk(combined, section, subsection))
        else:
            for chunk_text in _split_paragraphs(pending_paragraphs):
                chunks.append(make_chunk(chunk_text, section, subsection))
        pending_paragraphs.clear()

    def handle_h2(heading_text: str) -> None:
        nonlocal current_h2, current_h3, skip_section
        flush(current_h2, current_h3)
        current_h2 = heading_text
        current_h3 = ""
        skip_section = heading_text.lower() in _BLOCKED_SECTIONS

    def handle_h3(heading_text: str) -> None:
        nonlocal current_h3
        flush(current_h2, current_h3)
        current_h3 = heading_text

    def handle_p(text: str) -> None:
        if not skip_section and text:
            pending_paragraphs.append(text)

    for el in main.children:
        if not isinstance(el, Tag):
            continue

        if el.name == "h2":
            handle_h2(_clean_text(el.get_text()))

        elif el.name == "h3":
            handle_h3(_clean_text(el.get_text()))

        elif el.name == "p":
            handle_p(_clean_text(el.get_text()))

        elif el.name in ("div", "section"):
            # Recurse one level for nested content blocks
            for child in el.children:
                if not isinstance(child, Tag):
                    continue
                if child.name == "h2":
                    handle_h2(_clean_text(child.get_text()))
                elif child.name == "h3":
                    handle_h3(_clean_text(child.get_text()))
                elif child.name == "p":
                    handle_p(_clean_text(child.get_text()))

    flush(current_h2, current_h3)
    return chunks


def chunk_all_sep(data_dir: Path) -> list[dict]:
    """
    Read sources.json from data_dir/sep/, chunk every SEP HTML file listed,
    and return the combined chunk list.
    """
    sep_dir = data_dir / "sep"
    manifest_path = sep_dir / "sources.json"
    manifest: list[dict] = json.loads(manifest_path.read_text(encoding="utf-8"))

    all_chunks: list[dict] = []
    for entry in manifest:
        html_path = sep_dir / entry["file"]
        if not html_path.exists():
            print(f"  [WARN] Missing SEP file: {html_path}")
            continue
        file_chunks = chunk_sep_file(html_path, entry)
        print(f"  SEP '{entry['id']}': {len(file_chunks)} chunks")
        all_chunks.extend(file_chunks)

    return all_chunks
