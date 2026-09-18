"""Fetch SEP source entries for RAG indexing.

Run from anywhere: python scripts/fetch_sources.py

By default, skips files that already exist. Pass --force to re-download all.
"""
import argparse
import json
import urllib.request
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data" / "sep"

SOURCES = [
    {"id": "liberalism",           "url": "https://plato.stanford.edu/entries/liberalism/",           "title": "Liberalism"},
    {"id": "mill-moral-political", "url": "https://plato.stanford.edu/entries/mill-moral-political/", "title": "Mill's Moral and Political Philosophy"},
    {"id": "mill",                 "url": "https://plato.stanford.edu/entries/mill/",                 "title": "John Stuart Mill"},
    {"id": "democracy",            "url": "https://plato.stanford.edu/entries/democracy/",            "title": "Democracy"},
    {"id": "rousseau",             "url": "https://plato.stanford.edu/entries/rousseau/",             "title": "Jean Jacques Rousseau"},
]

def load_existing_manifest(manifest_path: Path) -> dict:
    """Return {id: entry} from existing manifest, or empty dict."""
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text())
        return {entry["id"]: entry for entry in data}
    except (json.JSONDecodeError, KeyError):
        return {}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if files exist")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = DATA_DIR / "sources.json"
    existing = load_existing_manifest(manifest_path)

    today = date.today().isoformat()
    manifest = []

    for src in SOURCES:
        filename = f"{src['id']}.html"
        outpath = DATA_DIR / filename
        prev = existing.get(src["id"])

        if outpath.exists() and not args.force:
            accessed = prev["accessed"] if prev else today
            print(f"Skip   {filename} (exists, accessed {accessed})")
        else:
            print(f"Fetch  {filename}")
            urllib.request.urlretrieve(src["url"], outpath)
            accessed = today

        manifest.append({**src, "file": filename, "accessed": accessed})

    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote manifest with {len(manifest)} entries to {manifest_path}")

if __name__ == "__main__":
    main()