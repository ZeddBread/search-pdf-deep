#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from pdf_search_core import search_pdfs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("query")
    ap.add_argument("--regex", action="store_true")
    ap.add_argument("--ignore-case", action="store_true")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--include-ocr", action="store_true")
    ap.add_argument("--ocr-dpi", type=int, default=200)
    args = ap.parse_args()

    results = search_pdfs(
        Path(args.folder),
        args.query,
        recursive=args.recursive,
        use_regex=args.regex,
        ignore_case=args.ignore_case,
        include_ocr=args.include_ocr,
        ocr_dpi=args.ocr_dpi,
    )

    for m in results:
        tag = " [OCR]" if m.used_ocr else ""
        print(f"{m.pdf_path} | page {m.page_number_1based}{tag} | {m.snippet}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
