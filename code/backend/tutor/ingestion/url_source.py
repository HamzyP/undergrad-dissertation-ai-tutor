"""
Generic URL fetching and chunking.

Fetches any webpage, strips boilerplate, and splits paragraph text into
≤500-token chunks using the same strategy as the SEP ingester.
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import tiktoken
from bs4 import BeautifulSoup, Tag

_enc = tiktoken.get_encoding("cl100k_base")
_MAX_TOKENS = 500

_BOILERPLATE_IDS = [
    "toc", "bibliography", "academic-tools", "other-internet-resources",
    "related-entries", "footer", "navigation", "sidebar", "header",
    "header-wrapper", "site-footer", "cookie-banner", "cookie-notice",
]
_BOILERPLATE_CLASSES = re.compile(
    r"(sidebar|footer|nav|toc|bibliography|cookie|banner|advertisement|ad-|"
    r"social|share|comment|related|breadcrumb)",
    re.I,
)


def _count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _strip_boilerplate(soup: BeautifulSoup) -> None:
    for id_ in _BOILERPLATE_IDS:
        el = soup.find(id=id_)
        if el:
            el.decompose()
    for el in soup.find_all(class_=_BOILERPLATE_CLASSES):
        el.decompose()
    for tag in soup.find_all(["script", "style", "noscript", "iframe", "nav", "header", "footer"]):
        tag.decompose()


def _extract_title(soup: BeautifulSoup) -> str:
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return _clean(str(og["content"]))
    h1 = soup.find("h1")
    if h1:
        return _clean(h1.get_text())
    title = soup.find("title")
    if title:
        return _clean(title.get_text())
    return ""


def _split_paragraphs(paragraphs: list[str], max_tokens: int = _MAX_TOKENS) -> list[str]:
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


def _url_to_source_id(url: str) -> str:
    """Derive a stable, filesystem-safe source_id from a URL."""
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "-") or parsed.netloc
    # keep only safe characters
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "-", f"{parsed.netloc}-{path}")
    safe = re.sub(r"-{2,}", "-", safe).strip("-")
    return safe[:80]


def fetch_and_chunk(url: str, source_id: str, title: str) -> list[dict]:
    """
    Fetch a URL, extract readable paragraph text, and return chunk dicts.

    Each chunk:
        {
            "text": str,
            "metadata": {
                "source_id": str,
                "source_type": "sep",   # kept as "sep" for ChromaDB compatibility
                "title": str,
                "url": str,
                "section": str,
                "subsection": str,
                "chunk_index": int,
            }
        }
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TutorRAG/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")
    _strip_boilerplate(soup)

    if not title:
        title = _extract_title(soup)

    # Prefer a prominent content container; fall back to body
    main = (
        soup.find(id="main-text")
        or soup.find(id="main-content")
        or soup.find(id="content")
        or soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"(entry-content|post-content|article-body|content)", re.I))
        or soup.body
    )
    if main is None:
        return []

    chunks: list[dict] = []
    chunk_index = 0
    current_h2 = ""
    current_h3 = ""
    pending: list[str] = []

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

    def flush(section: str, subsection: str) -> None:
        if not pending:
            return
        combined = " ".join(pending)
        if _count_tokens(combined) <= _MAX_TOKENS:
            chunks.append(make_chunk(combined, section, subsection))
        else:
            for text in _split_paragraphs(pending):
                chunks.append(make_chunk(text, section, subsection))
        pending.clear()

    def walk(el: Tag) -> None:
        nonlocal current_h2, current_h3
        for child in el.children:
            if not isinstance(child, Tag):
                continue
            name = child.name
            if name == "h2":
                flush(current_h2, current_h3)
                current_h2 = _clean(child.get_text())
                current_h3 = ""
            elif name == "h3":
                flush(current_h2, current_h3)
                current_h3 = _clean(child.get_text())
            elif name == "p":
                text = _clean(child.get_text())
                if text:
                    pending.append(text)
            elif name in ("div", "section", "article", "main"):
                walk(child)

    walk(main)
    flush(current_h2, current_h3)
    return chunks
