#!/usr/bin/env python3
"""Extract SRD 5.2.1 text per page and build a heading index.

Outputs (gitignored, derived from the pinned PDF):
  sources/text/page-NNN.txt   raw text per page
  sources/index.json          bookmark/outline tree with page numbers
"""

import json
import pathlib
import sys

from pypdf import PdfReader

SRC = pathlib.Path(__file__).parent
PDF = SRC / "SRD_CC_v5.2.1.pdf"
OUT = SRC / "text"


def walk_outline(reader, items, depth=0):
    entries = []
    for item in items:
        if isinstance(item, list):
            entries.extend(walk_outline(reader, item, depth + 1))
        else:
            try:
                page = reader.get_destination_page_number(item)
            except Exception:
                page = None
            entries.append({"title": str(item.title), "page": page, "depth": depth})
    return entries


def main():
    if not PDF.exists():
        sys.exit("Run fetch.sh first — SRD PDF not found.")
    reader = PdfReader(PDF)
    OUT.mkdir(exist_ok=True)

    for i, page in enumerate(reader.pages, start=1):
        (OUT / f"page-{i:03d}.txt").write_text(page.extract_text() or "")

    index = walk_outline(reader, reader.outline) if reader.outline else []
    (SRC / "index.json").write_text(json.dumps(index, indent=1))
    print(f"pages: {len(reader.pages)}, outline entries: {len(index)}")


if __name__ == "__main__":
    main()
