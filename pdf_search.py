#!/usr/bin/env python3
"""
Search text inside all PDFs in a folder and print matches with file + page number.

Usage:
  python pdf_search.py "C:\path\to\pdfs" "search phrase"
  python pdf_search.py /path/to/pdfs "search phrase" --regex
  python pdf_search.py /path/to/pdfs "search phrase" --ignore-case
  python pdf_search.py /path/to/pdfs "search phrase" --include-ocr
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# Text extraction (fast, works for text-based PDFs)
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

# Optional OCR (slow, only needed for scanned/image PDFs)
try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None


@dataclass
class Match:
    pdf_path: Path
    page_number_1based: int
    snippet: str


def _normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _make_snippet(text: str, start: int, end: int, radius: int = 60) -> str:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    snippet = text[lo:hi]
    snippet = _normalize_whitespace(snippet)
    return snippet


def _compile_pattern(query: str, use_regex: bool, ignore_case: bool) -> re.Pattern:
    flags = re.DOTALL
    if ignore_case:
        flags |= re.IGNORECASE
    if use_regex:
        return re.compile(query, flags)
    # literal search
    return re.compile(re.escape(query), flags)


def _extract_text_pymupdf(doc: "fitz.Document", page_index: int) -> str:
    page = doc.load_page(page_index)
    # "text" is usually best for searching
    return page.get_text("text") or ""


def _page_needs_ocr(text: str, min_chars: int = 25) -> bool:
    # If very little text is extractable, it is often a scanned page
    return len(_normalize_whitespace(text)) < min_chars


def _ocr_page(doc: "fitz.Document", page_index: int, dpi: int = 200) -> str:
    if pytesseract is None or Image is None:
        raise RuntimeError(
            "OCR requested but pytesseract/Pillow not installed. "
            "Install with: pip install pytesseract pillow"
        )
    page = doc.load_page(page_index)
    pix = page.get_pixmap(dpi=dpi)
    mode = "RGB" if pix.alpha == 0 else "RGBA"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img) or ""


def search_pdf(
    pdf_path: Path,
    pattern: re.Pattern,
    include_ocr: bool,
    ocr_dpi: int,
) -> List[Match]:
    if fitz is None:
        raise RuntimeError("PyMuPDF not installed. Install with: pip install pymupdf")

    matches: List[Match] = []
    try:
        with fitz.open(pdf_path) as doc:
            for i in range(doc.page_count):
                text = _extract_text_pymupdf(doc, i)
                used_ocr = False

                if include_ocr and _page_needs_ocr(text):
                    try:
                        text = _ocr_page(doc, i, dpi=ocr_dpi)
                        used_ocr = True
                    except Exception:
                        # OCR failed; fall back to extracted text (even if sparse)
                        pass

                if not text:
                    continue

                for m in pattern.finditer(text):
                    snippet = _make_snippet(text, m.start(), m.end())
                    if used_ocr:
                        snippet = f"[OCR] {snippet}"
                    matches.append(
                        Match(pdf_path=pdf_path, page_number_1based=i + 1, snippet=snippet)
                    )
    except Exception as e:
        print(f"ERROR reading {pdf_path}: {e}", file=sys.stderr)

    return matches


def iter_pdfs(folder: Path, recursive: bool) -> Iterable[Path]:
    if recursive:
        yield from folder.rglob("*.pdf")
    else:
        yield from folder.glob("*.pdf")


def main() -> int:
    ap = argparse.ArgumentParser(description="Search text inside PDFs and report file + page number.")
    ap.add_argument("folder", type=str, help="Folder containing PDFs")
    ap.add_argument("query", type=str, help="Text to search for (literal by default)")
    ap.add_argument("--regex", action="store_true", help="Treat query as a regular expression")
    ap.add_argument("--ignore-case", action="store_true", help="Case-insensitive search")
    ap.add_argument("--recursive", action="store_true", help="Search PDFs in subfolders too")
    ap.add_argument("--include-ocr", action="store_true", help="OCR pages with little/no extractable text (slower)")
    ap.add_argument("--ocr-dpi", type=int, default=200, help="OCR render DPI (default: 200)")
    ap.add_argument("--no-snippet", action="store_true", help="Do not print text snippets")
    args = ap.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"Folder not found: {folder}", file=sys.stderr)
        return 2

    pattern = _compile_pattern(args.query, args.regex, args.ignore_case)

    pdfs = list(iter_pdfs(folder, args.recursive))
    if not pdfs:
        print("No PDFs found.", file=sys.stderr)
        return 1

    total = 0
    for pdf in sorted(pdfs):
        hits = search_pdf(pdf, pattern, args.include_ocr, args.ocr_dpi)
        for h in hits:
            total += 1
            rel = h.pdf_path.relative_to(folder) if h.pdf_path.is_relative_to(folder) else h.pdf_path
            if args.no_snippet:
                print(f"{rel} | page {h.page_number_1based}")
            else:
                print(f"{rel} | page {h.page_number_1based} | {h.snippet}")

    if total == 0:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
