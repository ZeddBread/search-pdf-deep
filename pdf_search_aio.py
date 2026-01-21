#!/usr/bin/env python3
"""
PDF Search GUI (Windows-friendly, modern look)

Features
- Folder picker
- Literal or Regex search, case-insensitive, recursive
- Optional OCR for scanned pages (slow)
- Progress bar + cancel
- Results table with File, Page, Snippet
- Double click result to open PDF (default app)
- Buttons: Open file, Open folder, Copy path, Export CSV

Dependencies
- pip install pymupdf customtkinter
Optional OCR
- pip install pytesseract pillow
- Install Tesseract OCR and ensure tesseract.exe is on PATH (or set it in Settings below)

Run
- python pdf_search_gui.py
"""

from __future__ import annotations

import csv
import os
import queue
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

# Optional OCR
try:
    import pytesseract
    from PIL import Image
except Exception:
    pytesseract = None
    Image = None


# -------------------------
# Settings you may edit
# -------------------------
# If OCR is enabled and Tesseract isn't on PATH, set this to your tesseract.exe path, e.g.:
# TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT_CMD = ""


@dataclass
class Match:
    pdf_path: Path
    page_number_1based: int
    snippet: str


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


def page_needs_ocr(text: str, min_chars: int = 25) -> bool:
    return len(normalize_whitespace(text)) < min_chars


def extract_text_pymupdf(doc: "fitz.Document", page_index: int) -> str:
    page = doc.load_page(page_index)
    return page.get_text("text") or ""


def ocr_page(doc: "fitz.Document", page_index: int, dpi: int = 200) -> str:
    if pytesseract is None or Image is None:
        raise RuntimeError("OCR not available. Install pytesseract + pillow.")
    page = doc.load_page(page_index)
    pix = page.get_pixmap(dpi=dpi)
    mode = "RGB" if pix.alpha == 0 else "RGBA"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img) or ""


def iter_pdfs(folder: Path, recursive: bool) -> List[Path]:
    if recursive:
        return sorted(folder.rglob("*.pdf"))
    return sorted(folder.glob("*.pdf"))


class PDFSearchApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("PDF Search")
        self.geometry("1150x720")
        self.minsize(980, 620)

        self._worker: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ui_queue: "queue.Queue[tuple]" = queue.Queue()

        self._results: List[Match] = []

        self._build_ui()
        self.after(50, self._poll_queue)

    # -------------------------
    # UI
    # -------------------------
    def _build_ui(self) -> None:
        # Top: inputs
        top = ctk.CTkFrame(self, corner_radius=16)
        top.pack(fill="x", padx=16, pady=(16, 10))

        grid = top

        self.folder_var = tk.StringVar(value=str(Path.home()))
        self.query_var = tk.StringVar(value="")
        self.regex_var = tk.BooleanVar(value=False)
        self.ignore_case_var = tk.BooleanVar(value=True)
        self.recursive_var = tk.BooleanVar(value=True)
        self.ocr_var = tk.BooleanVar(value=False)
        self.ocr_dpi_var = tk.IntVar(value=200)

        # Row 0: folder
        ctk.CTkLabel(grid, text="Folder", width=60, anchor="w").grid(row=0, column=0, padx=(14, 8), pady=(14, 8), sticky="w")
        self.folder_entry = ctk.CTkEntry(grid, textvariable=self.folder_var)
        self.folder_entry.grid(row=0, column=1, padx=(0, 10), pady=(14, 8), sticky="ew")
        ctk.CTkButton(grid, text="Browse", width=110, command=self._pick_folder).grid(row=0, column=2, padx=(0, 14), pady=(14, 8))

        # Row 1: query
        ctk.CTkLabel(grid, text="Search", width=60, anchor="w").grid(row=1, column=0, padx=(14, 8), pady=(0, 12), sticky="w")
        self.query_entry = ctk.CTkEntry(grid, textvariable=self.query_var, placeholder_text="Type text to find...")
        self.query_entry.grid(row=1, column=1, padx=(0, 10), pady=(0, 12), sticky="ew")
        self.search_btn = ctk.CTkButton(grid, text="Search", width=110, command=self._start_search)
        self.search_btn.grid(row=1, column=2, padx=(0, 14), pady=(0, 12))

        grid.grid_columnconfigure(1, weight=1)

        # Options row
        opts = ctk.CTkFrame(self, corner_radius=16)
        opts.pack(fill="x", padx=16, pady=(0, 10))

        c1 = ctk.CTkCheckBox(opts, text="Regex", variable=self.regex_var)
        c2 = ctk.CTkCheckBox(opts, text="Ignore case", variable=self.ignore_case_var)
        c3 = ctk.CTkCheckBox(opts, text="Recursive", variable=self.recursive_var)
        c4 = ctk.CTkCheckBox(opts, text="OCR scanned pages (slow)", variable=self.ocr_var)

        c1.grid(row=0, column=0, padx=(14, 10), pady=(12, 12), sticky="w")
        c2.grid(row=0, column=1, padx=(0, 10), pady=(12, 12), sticky="w")
        c3.grid(row=0, column=2, padx=(0, 10), pady=(12, 12), sticky="w")
        c4.grid(row=0, column=3, padx=(0, 10), pady=(12, 12), sticky="w")

        ctk.CTkLabel(opts, text="OCR DPI").grid(row=0, column=4, padx=(10, 6), pady=(12, 12), sticky="e")
        self.ocr_dpi = ctk.CTkEntry(opts, width=80, textvariable=self.ocr_dpi_var)
        self.ocr_dpi.grid(row=0, column=5, padx=(0, 14), pady=(12, 12), sticky="w")

        opts.grid_columnconfigure(6, weight=1)

        self.cancel_btn = ctk.CTkButton(opts, text="Cancel", width=110, state="disabled", command=self._cancel_search)
        self.cancel_btn.grid(row=0, column=7, padx=(0, 14), pady=(12, 12), sticky="e")

        # Progress
        prog = ctk.CTkFrame(self, corner_radius=16)
        prog.pack(fill="x", padx=16, pady=(0, 10))

        self.status_var = tk.StringVar(value="Ready.")
        self.progress_var = tk.DoubleVar(value=0.0)

        self.status_lbl = ctk.CTkLabel(prog, textvariable=self.status_var, anchor="w")
        self.status_lbl.pack(fill="x", padx=14, pady=(12, 6))

        self.progress = ctk.CTkProgressBar(prog)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=14, pady=(0, 12))

        # Results toolbar
        bar = ctk.CTkFrame(self, corner_radius=16)
        bar.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkLabel(bar, text="Results").pack(side="left", padx=14, pady=12)

        self.count_var = tk.StringVar(value="0 matches")
        ctk.CTkLabel(bar, textvariable=self.count_var).pack(side="left", padx=(0, 14), pady=12)

        ctk.CTkButton(bar, text="Export CSV", width=120, command=self._export_csv).pack(side="right", padx=(8, 14), pady=12)
        ctk.CTkButton(bar, text="Copy Path", width=120, command=self._copy_selected_path).pack(side="right", padx=(8, 0), pady=12)
        ctk.CTkButton(bar, text="Open Folder", width=120, command=self._open_selected_folder).pack(side="right", padx=(8, 0), pady=12)
        ctk.CTkButton(bar, text="Open File", width=120, command=self._open_selected_file).pack(side="right", padx=(8, 0), pady=12)

        # Results table (ttk Treeview inside a CTkFrame)
        table_wrap = ctk.CTkFrame(self, corner_radius=16)
        table_wrap.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        style = ttk.Style()
        # Use the native theme; customtkinter handles the frame, Treeview stays native.
        try:
            style.theme_use("vista")
        except Exception:
            pass

        columns = ("file", "page", "snippet")
        self.tree = ttk.Treeview(table_wrap, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("file", text="File")
        self.tree.heading("page", text="Page")
        self.tree.heading("snippet", text="Snippet")

        self.tree.column("file", width=420, anchor="w")
        self.tree.column("page", width=70, anchor="center")
        self.tree.column("snippet", width=600, anchor="w")

        vsb = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.pack(side="top", fill="both", expand=True, padx=14, pady=(14, 0))
        vsb.place(in_=self.tree, relx=1.0, rely=0, relheight=1.0, anchor="ne")
        hsb.pack(side="bottom", fill="x", padx=14, pady=(0, 14))

        self.tree.bind("<Double-1>", lambda _e: self._open_selected_file())

    # -------------------------
    # Actions
    # -------------------------
    def _pick_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.folder_var.get() or str(Path.home()))
        if chosen:
            self.folder_var.set(chosen)

    def _set_busy(self, busy: bool) -> None:
        self.search_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        self.folder_entry.configure(state="disabled" if busy else "normal")
        self.query_entry.configure(state="disabled" if busy else "normal")

    def _start_search(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        if fitz is None:
            messagebox.showerror("Missing dependency", "PyMuPDF is not installed. Run: pip install pymupdf")
            return

        folder = Path(self.folder_var.get()).expanduser()
        if not folder.exists() or not folder.is_dir():
            messagebox.showerror("Invalid folder", "Please select a valid folder.")
            return

        query = self.query_var.get().strip()
        if not query:
            messagebox.showerror("Missing search", "Please enter search text.")
            return

        if self.ocr_var.get():
            if pytesseract is None or Image is None:
                messagebox.showerror("OCR not available", "Install OCR deps: pip install pytesseract pillow")
                return
            if TESSERACT_CMD:
                pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

        # Clear previous
        self._results = []
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.count_var.set("0 matches")
        self.status_var.set("Starting...")
        self.progress.set(0)

        self._stop_event.clear()
        self._set_busy(True)

        args = {
            "folder": folder,
            "query": query,
            "use_regex": bool(self.regex_var.get()),
            "ignore_case": bool(self.ignore_case_var.get()),
            "recursive": bool(self.recursive_var.get()),
            "include_ocr": bool(self.ocr_var.get()),
            "ocr_dpi": int(self.ocr_dpi_var.get() or 200),
        }

        self._worker = threading.Thread(target=self._search_worker, kwargs=args, daemon=True)
        self._worker.start()

    def _cancel_search(self) -> None:
        self._stop_event.set()
        self.status_var.set("Cancelling...")

    def _search_worker(
        self,
        folder: Path,
        query: str,
        use_regex: bool,
        ignore_case: bool,
        recursive: bool,
        include_ocr: bool,
        ocr_dpi: int,
    ) -> None:
        t0 = time.time()
        try:
            pattern = compile_pattern(query, use_regex, ignore_case)
        except re.error as e:
            self._ui_queue.put(("error", f"Regex error: {e}"))
            self._ui_queue.put(("done",))
            return

        pdfs = iter_pdfs(folder, recursive)
        if not pdfs:
            self._ui_queue.put(("status", "No PDFs found."))
            self._ui_queue.put(("progress", 0.0))
            self._ui_queue.put(("done",))
            return

        self._ui_queue.put(("status", f"Found {len(pdfs)} PDFs. Searching..."))

        total_pages = 0
        # First pass: count pages (fast enough, gives better progress)
        try:
            for p in pdfs:
                if self._stop_event.is_set():
                    self._ui_queue.put(("done",))
                    return
                with fitz.open(p) as d:
                    total_pages += d.page_count
        except Exception:
            # fallback: progress by file count
            total_pages = 0

        scanned = 0
        processed_pages = 0
        found = 0

        for idx, pdf_path in enumerate(pdfs, start=1):
            if self._stop_event.is_set():
                break

            try:
                with fitz.open(pdf_path) as doc:
                    for page_i in range(doc.page_count):
                        if self._stop_event.is_set():
                            break

                        text = extract_text_pymupdf(doc, page_i)
                        used_ocr = False

                        if include_ocr and page_needs_ocr(text):
                            scanned += 1
                            try:
                                text = ocr_page(doc, page_i, dpi=ocr_dpi)
                                used_ocr = True
                            except Exception:
                                # OCR failure: continue with extracted text
                                pass

                        if text:
                            for m in pattern.finditer(text):
                                snippet = make_snippet(text, m.start(), m.end())
                                if used_ocr:
                                    snippet = f"[OCR] {snippet}"
                                match = Match(pdf_path=pdf_path, page_number_1based=page_i + 1, snippet=snippet)
                                self._ui_queue.put(("match", match))
                                found += 1

                        processed_pages += 1
                        if total_pages > 0:
                            self._ui_queue.put(("progress", processed_pages / total_pages))

                self._ui_queue.put(("status", f"Searching {idx}/{len(pdfs)}: {pdf_path.name} | matches: {found}"))
            except Exception as e:
                self._ui_queue.put(("status", f"Error reading {pdf_path.name}: {e}"))

            if total_pages == 0:
                self._ui_queue.put(("progress", idx / len(pdfs)))

        elapsed = time.time() - t0
        if self._stop_event.is_set():
            self._ui_queue.put(("status", f"Cancelled. {found} matches so far."))
        else:
            extra = f" | OCR pages: {scanned}" if include_ocr else ""
            self._ui_queue.put(("status", f"Done. {found} matches in {elapsed:.1f}s{extra}."))
            self._ui_queue.put(("progress", 1.0))

        self._ui_queue.put(("done",))

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._ui_queue.get_nowait()
                kind = msg[0]

                if kind == "status":
                    self.status_var.set(msg[1])

                elif kind == "progress":
                    v = float(msg[1])
                    v = 0.0 if v < 0 else 1.0 if v > 1 else v
                    self.progress.set(v)

                elif kind == "match":
                    match: Match = msg[1]
                    self._results.append(match)
                    self._insert_match(match)
                    self.count_var.set(f"{len(self._results)} matches")

                elif kind == "error":
                    messagebox.showerror("Error", msg[1])

                elif kind == "done":
                    self._set_busy(False)

        except queue.Empty:
            pass

        self.after(50, self._poll_queue)

    def _insert_match(self, match: Match) -> None:
        # display file relative to search folder when possible
        base = Path(self.folder_var.get()).expanduser().resolve()
        try:
            shown = str(match.pdf_path.resolve().relative_to(base))
        except Exception:
            shown = str(match.pdf_path)
        self.tree.insert("", "end", values=(shown, match.page_number_1based, match.snippet))

    # -------------------------
    # Result interactions
    # -------------------------
    def _get_selected_index(self) -> Optional[int]:
        sel = self.tree.selection()
        if not sel:
            return None
        item_id = sel[0]
        # Tree order matches _results append order
        idx = self.tree.index(item_id)
        if idx < 0 or idx >= len(self._results):
            return None
        return idx

    def _open_selected_file(self) -> None:
        idx = self._get_selected_index()
        if idx is None:
            return
        path = self._results[idx].pdf_path
        try:
            os.startfile(str(path))  # Windows
        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    def _open_selected_folder(self) -> None:
        idx = self._get_selected_index()
        if idx is None:
            return
        folder = self._results[idx].pdf_path.parent
        try:
            os.startfile(str(folder))
        except Exception as e:
            messagebox.showerror("Open folder failed", str(e))

    def _copy_selected_path(self) -> None:
        idx = self._get_selected_index()
        if idx is None:
            return
        path = str(self._results[idx].pdf_path)
        self.clipboard_clear()
        self.clipboard_append(path)
        self.status_var.set("Copied file path to clipboard.")

    def _export_csv(self) -> None:
        if not self._results:
            messagebox.showinfo("Nothing to export", "No results to export yet.")
            return

        default_name = f"pdf_search_results_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        out = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv")],
        )
        if not out:
            return

        try:
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["file", "page", "snippet"])
                for m in self._results:
                    w.writerow([str(m.pdf_path), m.page_number_1based, m.snippet])
            self.status_var.set(f"Exported CSV: {out}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))


def main() -> int:
    app = PDFSearchApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
