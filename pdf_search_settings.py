from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional


APP_NAME = "PDFSearch"


def _appdata_dir() -> Path:
    # Windows: %APPDATA%\PDFSearch
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    # Fallback
    return Path.home() / f".{APP_NAME.lower()}"


def settings_path() -> Path:
    return _appdata_dir() / "settings.json"


@dataclass
class Settings:
    last_folder: str = ""
    regex: bool = False
    ignore_case: bool = True
    recursive: bool = True
    ocr: bool = False
    ocr_dpi: int = 200

    # Optional UI state
    window_geometry: str = ""  # e.g. "1150x720+120+80"


def load_settings() -> Settings:
    path = settings_path()
    try:
        if not path.exists():
            return Settings()
        data = json.loads(path.read_text(encoding="utf-8"))
        return _merge_settings(Settings(), data)
    except Exception:
        return Settings()


def save_settings(s: Settings) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")


def _merge_settings(defaults: Settings, data: Dict[str, Any]) -> Settings:
    d = asdict(defaults)
    for k, v in data.items():
        if k in d:
            d[k] = v
    # Basic type safety for DPI
    try:
        d["ocr_dpi"] = int(d.get("ocr_dpi", defaults.ocr_dpi))
    except Exception:
        d["ocr_dpi"] = defaults.ocr_dpi
    return Settings(**d)
