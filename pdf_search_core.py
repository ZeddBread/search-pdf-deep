from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Callable

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    import pytesseract
    from PIL import Image
except Exception:
    pytesseract = None
    Image = None


@dataclass(frozen=True)
class Match:
    pdf_path: Path
    page_number_1based: int
    snippet: str
    used_ocr: bool = False


@dataclass(frozen=True)
class Progress:
    processed: int
    total: int
    current_file: Optional[Path] = None
    matches_found: int = 0


def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def make_snippet(text: str, start: int, end: int, radius: int = 70) -> str:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    return normalize_whitespace(text[lo:hi])


def compile_pattern(query: str, use_regex: bool, ignore_case: bool) -> re.Pattern:
    flags = re.DOTALL
    if ignore_case:
        flags |= re.IGNORECASE
    if use_regex:
        return re.compile(query, flags)
    return re.compile(re.escape(query), flags)


def iter_pdfs(folder: Path, recursive: bool) -> List[Path]:
    folder = folder.expanduser().resolve()
    if recursive:
        return sorted(folder.rglob("*.pdf"))
    return sorted(folder.glob("*.pdf"))


def _extract_text_pymupdf(doc: "fitz.Document", page_index: int) -> str:
    page = doc.load_page(page_index)
    return page.get_text("text") or ""


def _page_needs_ocr(text: str, min_chars: int = 25) -> bool:
    return len(normalize_whitespace(text)) < min_chars


def _ocr_page(doc: "fitz.Document", page_index: int, dpi: int = 200) -> str:
    if pytesseract is None or Image is None:
        raise RuntimeError("OCR not available. Install: pip install pytesseract pillow")
    page = doc.load_page(page_index)
    pix = page.get_pixmap(dpi=dpi)
    mode = "RGB" if pix.alpha == 0 else "RGBA"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img) or ""


def count_total_pages(pdfs: List[Path]) -> int:
    if fitz is None:
        raise RuntimeError("PyMuPDF not installed. Install: pip install pymupdf")
    total = 0
    for p in pdfs:
        with fitz.open(p) as d:
            total += d.page_count
    return total


def search_pdfs(
    folder: Path,
    query: str,
    *,
    recursive: bool = True,
    use_regex: bool = False,
    ignore_case: bool = True,
    include_ocr: bool = False,
    ocr_dpi: int = 200,
    snippet_radius: int = 70,
    should_cancel: Optional[Callable[[], bool]] = None,
    on_progress: Optional[Callable[[Progress], None]] = None,
) -> List[Match]:
    """
    Searches PDFs and returns a list of Match.

    - should_cancel(): return True to stop early
    - on_progress(Progress): called occasionally
    """
    if fitz is None:
        raise RuntimeError("PyMuPDF not installed. Install: pip install pymupdf")

    folder = folder.expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Invalid folder: {folder}")

    q = (query or "").strip()
    if not q:
        raise ValueError("Query is empty")

    pattern = compile_pattern(q, use_regex, ignore_case)
    pdfs = iter_pdfs(folder, recursive)

    matches: List[Match] = []
    processed_pages = 0

    # Optional: compute total pages for accurate progress
    total_pages = 0
    try:
        total_pages = count_total_pages(pdfs) if pdfs else 0
    except Exception:
        total_pages = 0  # fallback to unknown total

    def cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    def progress(file_path: Optional[Path] = None) -> None:
        if on_progress:
            on_progress(
                Progress(
                    processed=processed_pages,
                    total=total_pages,
                    current_file=file_path,
                    matches_found=len(matches),
                )
            )

    progress(None)

    for pdf_path in pdfs:
        if cancelled():
            break

        progress(pdf_path)

        try:
            with fitz.open(pdf_path) as doc:
                for page_i in range(doc.page_count):
                    if cancelled():
                        break

                    text = _extract_text_pymupdf(doc, page_i)
                    used_ocr = False

                    if include_ocr and _page_needs_ocr(text):
                        try:
                            text = _ocr_page(doc, page_i, dpi=ocr_dpi)
                            used_ocr = True
                        except Exception:
                            # OCR failed, keep extracted text (even if sparse)
                            pass

                    if text:
                        for m in pattern.finditer(text):
                            snippet = make_snippet(text, m.start(), m.end(), radius=snippet_radius)
                            matches.append(
                                Match(
                                    pdf_path=pdf_path,
                                    page_number_1based=page_i + 1,
                                    snippet=snippet,
                                    used_ocr=used_ocr,
                                )
                            )

                    processed_pages += 1
                    if total_pages > 0 and processed_pages % 5 == 0:
                        progress(pdf_path)

        except Exception:
            # Ignore individual PDF failures, continue
            processed_pages += 0
            progress(pdf_path)

    progress(None)
    return matches
