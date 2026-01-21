from __future__ import annotations

import csv
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Optional, List

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from pdf_search_core import Match, Progress, search_pdfs

# Shared app logger (configured by launcher; safe if it isn't)
logger = logging.getLogger("pdf_search")

# If OCR is enabled and Tesseract isn't on PATH, set this:
# import pytesseract
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


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

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self, corner_radius=16)
        top.pack(fill="x", padx=16, pady=(16, 10))

        self.folder_var = tk.StringVar(value=str(Path.home()))
        self.query_var = tk.StringVar(value="")
        self.regex_var = tk.BooleanVar(value=False)
        self.ignore_case_var = tk.BooleanVar(value=True)
        self.recursive_var = tk.BooleanVar(value=True)
        self.ocr_var = tk.BooleanVar(value=False)
        self.ocr_dpi_var = tk.IntVar(value=200)

        ctk.CTkLabel(top, text="Folder", width=60, anchor="w").grid(row=0, column=0, padx=(14, 8), pady=(14, 8), sticky="w")
        self.folder_entry = ctk.CTkEntry(top, textvariable=self.folder_var)
        self.folder_entry.grid(row=0, column=1, padx=(0, 10), pady=(14, 8), sticky="ew")
        ctk.CTkButton(top, text="Browse", width=110, command=self._pick_folder).grid(row=0, column=2, padx=(0, 14), pady=(14, 8))

        ctk.CTkLabel(top, text="Search", width=60, anchor="w").grid(row=1, column=0, padx=(14, 8), pady=(0, 12), sticky="w")
        self.query_entry = ctk.CTkEntry(top, textvariable=self.query_var, placeholder_text="Type text to find...")
        self.query_entry.grid(row=1, column=1, padx=(0, 10), pady=(0, 12), sticky="ew")
        self.search_btn = ctk.CTkButton(top, text="Search", width=110, command=self._start_search)
        self.search_btn.grid(row=1, column=2, padx=(0, 14), pady=(0, 12))

        top.grid_columnconfigure(1, weight=1)

        opts = ctk.CTkFrame(self, corner_radius=16)
        opts.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkCheckBox(opts, text="Regex", variable=self.regex_var).grid(row=0, column=0, padx=(14, 10), pady=(12, 12), sticky="w")
        ctk.CTkCheckBox(opts, text="Ignore case", variable=self.ignore_case_var).grid(row=0, column=1, padx=(0, 10), pady=(12, 12), sticky="w")
        ctk.CTkCheckBox(opts, text="Recursive", variable=self.recursive_var).grid(row=0, column=2, padx=(0, 10), pady=(12, 12), sticky="w")
        ctk.CTkCheckBox(opts, text="OCR scanned pages (slow)", variable=self.ocr_var).grid(row=0, column=3, padx=(0, 10), pady=(12, 12), sticky="w")

        ctk.CTkLabel(opts, text="OCR DPI").grid(row=0, column=4, padx=(10, 6), pady=(12, 12), sticky="e")
        self.ocr_dpi = ctk.CTkEntry(opts, width=80, textvariable=self.ocr_dpi_var)
        self.ocr_dpi.grid(row=0, column=5, padx=(0, 14), pady=(12, 12), sticky="w")

        opts.grid_columnconfigure(6, weight=1)
        self.cancel_btn = ctk.CTkButton(opts, text="Cancel", width=110, state="disabled", command=self._cancel_search)
        self.cancel_btn.grid(row=0, column=7, padx=(0, 14), pady=(12, 12), sticky="e")

        prog = ctk.CTkFrame(self, corner_radius=16)
        prog.pack(fill="x", padx=16, pady=(0, 10))

        self.status_var = tk.StringVar(value="Ready.")
        self.status_lbl = ctk.CTkLabel(prog, textvariable=self.status_var, anchor="w")
        self.status_lbl.pack(fill="x", padx=14, pady=(12, 6))

        self.progress = ctk.CTkProgressBar(prog)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=14, pady=(0, 12))

        bar = ctk.CTkFrame(self, corner_radius=16)
        bar.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkLabel(bar, text="Results").pack(side="left", padx=14, pady=12)
        self.count_var = tk.StringVar(value="0 matches")
        ctk.CTkLabel(bar, textvariable=self.count_var).pack(side="left", padx=(0, 14), pady=12)

        ctk.CTkButton(bar, text="Export CSV", width=120, command=self._export_csv).pack(side="right", padx=(8, 14), pady=12)
        ctk.CTkButton(bar, text="Copy Path", width=120, command=self._copy_selected_path).pack(side="right", padx=(8, 0), pady=12)
        ctk.CTkButton(bar, text="Open Folder", width=120, command=self._open_selected_folder).pack(side="right", padx=(8, 0), pady=12)
        ctk.CTkButton(bar, text="Open File", width=120, command=self._open_selected_file).pack(side="right", padx=(8, 0), pady=12)

        table_wrap = ctk.CTkFrame(self, corner_radius=16)
        table_wrap.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        try:
            ttk.Style().theme_use("vista")
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

        folder = Path(self.folder_var.get()).expanduser()
        if not folder.exists() or not folder.is_dir():
            messagebox.showerror("Invalid folder", "Please select a valid folder.")
            return

        query = self.query_var.get().strip()
        if not query:
            messagebox.showerror("Missing search", "Please enter search text.")
            return

        for item in self.tree.get_children():
            self.tree.delete(item)
        self._results = []
        self.count_var.set("0 matches")
        self.status_var.set("Starting...")
        self.progress.set(0)

        self._stop_event.clear()
        self._set_busy(True)

        args = dict(
            folder=folder,
            query=query,
            recursive=bool(self.recursive_var.get()),
            use_regex=bool(self.regex_var.get()),
            ignore_case=bool(self.ignore_case_var.get()),
            include_ocr=bool(self.ocr_var.get()),
            ocr_dpi=int(self.ocr_dpi_var.get() or 200),
        )

        self._worker = threading.Thread(target=self._worker_run, kwargs=args, daemon=True)
        self._worker.start()

    def _cancel_search(self) -> None:
        self._stop_event.set()
        self.status_var.set("Cancelling...")

    def _worker_run(self, **kwargs) -> None:
        def should_cancel() -> bool:
            return self._stop_event.is_set()

        def on_progress(p: Progress) -> None:
            self._ui_queue.put(("progress", p))

        try:
            results = search_pdfs(
                should_cancel=should_cancel,
                on_progress=on_progress,
                **kwargs,
            )
            for m in results:
                self._ui_queue.put(("match", m))
            self._ui_queue.put(("done", False))
        except Exception as e:
            self._ui_queue.put(("error", str(e)))
            self._ui_queue.put(("done", True))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()

                if kind == "progress":
                    p: Progress = payload
                    if p.current_file:
                        self.status_var.set(f"Searching: {p.current_file.name} | matches: {p.matches_found}")
                    else:
                        self.status_var.set("Working...")

                    if p.total > 0:
                        self.progress.set(min(1.0, max(0.0, p.processed / p.total)))
                    else:
                        # unknown total, keep it moving gently
                        self.progress.set((time.time() % 1.0))

                elif kind == "match":
                    m: Match = payload
                    self._results.append(m)
                    self._insert_match(m)
                    self.count_var.set(f"{len(self._results)} matches")

                elif kind == "error":
                    messagebox.showerror("Error", payload)

                elif kind == "done":
                    _had_error = payload
                    if self._stop_event.is_set():
                        self.status_var.set(f"Cancelled. {len(self._results)} matches so far.")
                    else:
                        self.status_var.set(f"Done. {len(self._results)} matches.")
                        self.progress.set(1.0)
                    self._set_busy(False)

        except queue.Empty:
            pass

        self.after(50, self._poll_queue)

    def _insert_match(self, m: Match) -> None:
        base = Path(self.folder_var.get()).expanduser().resolve()
        try:
            shown = str(m.pdf_path.resolve().relative_to(base))
        except Exception:
            shown = str(m.pdf_path)
        snippet = f"[OCR] {m.snippet}" if m.used_ocr else m.snippet
        self.tree.insert("", "end", values=(shown, m.page_number_1based, snippet))

    def _get_selected_index(self) -> Optional[int]:
        sel = self.tree.selection()
        if not sel:
            return None
        idx = self.tree.index(sel[0])
        if 0 <= idx < len(self._results):
            return idx
        return None

    def _open_selected_file(self) -> None:
        idx = self._get_selected_index()
        if idx is None:
            return
        try:
            os.startfile(str(self._results[idx].pdf_path))
        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    def _open_selected_folder(self) -> None:
        idx = self._get_selected_index()
        if idx is None:
            return
        try:
            os.startfile(str(self._results[idx].pdf_path.parent))
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
                w.writerow(["file", "page", "used_ocr", "snippet"])
                for m in self._results:
                    w.writerow([str(m.pdf_path), m.page_number_1based, m.used_ocr, m.snippet])
            self.status_var.set(f"Exported CSV: {out}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))


def main() -> int:
    app = PDFSearchApp()
    # This runs once the event loop is active and the window exists.
    try:
        app.after(0, lambda: logger.info("PDF Search GUI started (mainloop running)."))
    except Exception:
        pass
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
