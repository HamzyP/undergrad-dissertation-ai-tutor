"""
VTT subtitle file parsing and chunking.

Aggregates WebVTT cues into overlapping time-window chunks.
"""

from __future__ import annotations

import re
from pathlib import Path

import webvtt


def _vtt_time_to_seconds(time_str: str) -> float:
    """Convert HH:MM:SS.mmm or MM:SS.mmm to seconds."""
    parts = time_str.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(parts[0])


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunk_vtt_file(vtt_path: Path) -> list[dict]:
    """
    Parse a single VTT file and return time-windowed chunks with 5-second overlap.

    Each chunk:
        {
            "text": str,
            "metadata": {
                "source_id": str,
                "source_type": "transcript",
                "topic": str,
                "start_time": float,
                "end_time": float,
                "chunk_index": int,
            }
        }
    """
    source_id = vtt_path.stem  # e.g. "liberalism" or "rep-democracy"

    cues = list(webvtt.read(str(vtt_path)))
    if not cues:
        return []

    # Build list of (start_seconds, end_seconds, text) for each cue
    cue_data: list[tuple[float, float, str]] = []
    for cue in cues:
        start = _vtt_time_to_seconds(cue.start)
        end = _vtt_time_to_seconds(cue.end)
        text = _clean_text(cue.text)
        if text:
            cue_data.append((start, end, text))

    if not cue_data:
        return []

    CHUNK_DURATION = 40.0  # seconds — soft target before looking for a sentence boundary
    CHUNK_MAX = 60.0       # seconds — hard cap; cut here even mid-sentence if needed
    OVERLAP = 15.0         # seconds to look back for the next chunk start
    MIN_DURATION = 15.0    # minimum seconds for a standalone tail chunk
    MIN_TOKENS = 40        # minimum tokens for a standalone tail chunk

    chunks: list[dict] = []
    chunk_index = 0
    i = 0  # pointer into cue_data

    while i < len(cue_data):
        chunk_start = cue_data[i][0]
        chunk_cues: list[tuple[float, float, str]] = []

        # Accumulate cues until the soft duration target is hit, then keep going
        # until the last cue ends on a sentence boundary or the hard cap is reached.
        j = i
        threshold_passed = False
        while j < len(cue_data):
            chunk_cues.append(cue_data[j])
            duration = cue_data[j][1] - chunk_start
            if duration >= CHUNK_DURATION:
                threshold_passed = True
            if threshold_passed:
                cue_text = cue_data[j][2].rstrip()
                if cue_text and cue_text[-1] in ".?!":
                    break  # clean sentence boundary reached
                if duration >= CHUNK_MAX:
                    break  # hard cap — cut here regardless
            j += 1

        if not chunk_cues:
            i += 1
            continue

        chunk_end = chunk_cues[-1][1]
        chunk_text = _clean_text(" ".join(c[2] for c in chunk_cues))

        # Detect degenerate tail chunk: merge into previous instead of emitting
        is_tail = j >= len(cue_data) - 1  # no cues remain after this
        too_short = (chunk_end - chunk_start) < MIN_DURATION
        too_few_tokens = len(chunk_text.split()) < MIN_TOKENS  # word count proxy
        if is_tail and (too_short or too_few_tokens) and chunks:
            prev = chunks[-1]
            prev["text"] = _clean_text(prev["text"] + " " + chunk_text)
            prev["metadata"]["end_time"] = chunk_end
            break

        chunks.append({
            "text": chunk_text,
            "metadata": {
                "source_id": source_id,
                "source_type": "transcript",
                "topic": source_id,
                "start_time": chunk_start,
                "end_time": chunk_end,
                "chunk_index": chunk_index,
            },
        })
        chunk_index += 1

        # Find start of next chunk: first cue with start >= chunk_end - OVERLAP
        overlap_start = chunk_end - OVERLAP
        next_i = len(cue_data)  # default: done
        for k in range(j + 1, len(cue_data)):
            if cue_data[k][0] >= overlap_start:
                next_i = k
                break
        else:
            # Try from current position forward
            for k in range(i + 1, len(cue_data)):
                if cue_data[k][0] >= overlap_start:
                    next_i = k
                    break

        if next_i >= len(cue_data):
            # No more cues beyond the overlap point — we're done
            break
        if next_i <= i:
            # Guard against infinite loop
            i = j + 1
        else:
            i = next_i

    return chunks


def chunk_all_transcripts(data_dir: Path) -> list[dict]:
    """
    Find all VTT files under data_dir/sep/transcripts/, chunk each,
    and return the combined chunk list.
    """
    transcript_dir = data_dir / "sep" / "transcripts"
    if not transcript_dir.exists():
        print(f"  [WARN] Transcript directory not found: {transcript_dir}")
        return []

    all_chunks: list[dict] = []
    for vtt_path in sorted(transcript_dir.glob("*.vtt")):
        file_chunks = chunk_vtt_file(vtt_path)
        print(f"  Transcript '{vtt_path.stem}': {len(file_chunks)} chunks")
        all_chunks.extend(file_chunks)

    return all_chunks
