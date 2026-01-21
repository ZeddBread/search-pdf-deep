from __future__ import annotations

import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

import multiprocessing as mp

from pdf_search_core import Match, Progress, search_pdfs


def _match_to_payload(m: Match) -> Dict[str, Any]:
    d = asdict(m)
    d["pdf_path"] = str(m.pdf_path)
    return d


def _progress_to_payload(p: Progress) -> Dict[str, Any]:
    return {
        "processed": p.processed,
        "total": p.total,
        "current_file": str(p.current_file) if p.current_file else None,
        "matches_found": p.matches_found,
    }


def search_worker(
    args: Dict[str, Any],
    out_queue: "mp.Queue",
    cancel_event: "mp.Event",
) -> None:
    """
    Runs in a child process. Sends messages to GUI via out_queue.

    Message shapes:
      {"type":"progress", "data":{...}}
      {"type":"match", "data":{...}}
      {"type":"done"}
      {"type":"error", "message":"..."}
    """
    try:
        folder = Path(args["folder"])
        query = args["query"]

        def should_cancel() -> bool:
            return cancel_event.is_set()

        def on_progress(p: Progress) -> None:
            out_queue.put({"type": "progress", "data": _progress_to_payload(p)})

        results = search_pdfs(
            folder=folder,
            query=query,
            recursive=bool(args.get("recursive", True)),
            use_regex=bool(args.get("use_regex", False)),
            ignore_case=bool(args.get("ignore_case", True)),
            include_ocr=bool(args.get("include_ocr", False)),
            ocr_dpi=int(args.get("ocr_dpi", 200)),
            snippet_radius=int(args.get("snippet_radius", 70)),
            should_cancel=should_cancel,
            on_progress=on_progress,
        )

        for m in results:
            out_queue.put({"type": "match", "data": _match_to_payload(m)})

        out_queue.put({"type": "done"})
    except Exception as e:
        out_queue.put({"type": "error", "message": f"{e}\n\n{traceback.format_exc()}"})
        out_queue.put({"type": "done"})
