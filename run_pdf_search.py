#!/usr/bin/env python3
"""
PDF Search Launcher

Single entry point for the application.
Safe place for:
- environment checks
- future logging
- packaging (PyInstaller)
"""

import sys
import traceback
from pathlib import Path


def _setup_logging() -> "object":
    """
    Configure logging to a file (and console when available).
    Returns a logger-like object.
    """
    import logging

    logger = logging.getLogger("pdf_search")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Log file: %APPDATA%\PDFSearch\app.log (fallback to ~/.pdfsearch/app.log)
    try:
        from pdf_search_settings import settings_path

        log_dir = settings_path().parent
    except Exception:
        log_dir = Path.home() / ".pdfsearch"

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        # If file logging fails, still attempt console logging below.
        pass

    try:
        sh = logging.StreamHandler(stream=sys.stderr)
        sh.setLevel(logging.INFO)
        fmt2 = logging.Formatter("%(levelname)s | %(message)s")
        sh.setFormatter(fmt2)
        logger.addHandler(sh)
    except Exception:
        pass

    return logger


def _run_pip_install(args: list[str]) -> None:
    """Run pip using the current Python interpreter."""
    import subprocess

    cmd = [sys.executable, "-m", "pip", *args]
    subprocess.run(cmd, check=True)


def _ensure_pip() -> None:
    """Ensure pip exists for this interpreter."""
    try:
        import pip  # noqa: F401
        return
    except Exception:
        pass

    try:
        import ensurepip

        ensurepip.bootstrap(upgrade=True)
    except Exception:
        # If ensurepip isn't available, pip install will fail below with a clearer error
        return


def _install_requirements(requirements_path: Path) -> None:
    """Install requirements from a requirements.txt file."""
    _ensure_pip()
    try:
        _run_pip_install(["install", "-r", str(requirements_path)])
    except Exception:
        # Fallback that often helps on Windows when global site-packages isn't writable
        _run_pip_install(["install", "--user", "-r", str(requirements_path)])


def _install_missing_module(module_name: str) -> None:
    """
    Install a missing module by mapping import name -> pip package name.
    If we can't map it, fall back to installing from requirements.txt.
    """
    import_name_to_pip = {
        # GUI
        "customtkinter": "customtkinter",
        # PDFs / OCR dependencies that may be missing in some envs
        "fitz": "pymupdf",
        "PIL": "pillow",
        "pytesseract": "pytesseract",
    }

    req = Path(__file__).with_name("requirements.txt")
    if req.exists():
        # Prefer installing the full requirements set so we're consistent
        _install_requirements(req)
        return

    pkg = import_name_to_pip.get(module_name, module_name)
    _ensure_pip()
    try:
        _run_pip_install(["install", pkg])
    except Exception:
        _run_pip_install(["install", "--user", pkg])


def main() -> int:
    logger = _setup_logging()
    try:
        logger.info("Launcher starting (python=%s)", sys.executable)
    except Exception:
        pass

    # Try to launch; if a dependency is missing, auto-install and retry once.
    attempts = 0
    while True:
        try:
            from pdf_search_gui import main as gui_main
            try:
                logger.info("Dependencies OK. Launching GUI...")
            except Exception:
                pass
            return gui_main()
        except ModuleNotFoundError as e:
            attempts += 1
            if attempts > 1:
                print("Failed to start PDF Search GUI.", file=sys.stderr)
                print(str(e), file=sys.stderr)
                traceback.print_exc()
                input("\nPress Enter to exit...")
                return 1

            missing = getattr(e, "name", None) or ""
            try:
                logger.warning("Missing dependency: %r. Installing requirements...", missing)
            except Exception:
                pass
            print(f"Missing dependency: {missing!r}. Installing requirements...", file=sys.stderr)
            try:
                _install_missing_module(missing)
            except Exception as install_err:
                try:
                    logger.exception("Auto-install failed.")
                except Exception:
                    pass
                print("Auto-install failed.", file=sys.stderr)
                print(str(install_err), file=sys.stderr)
                traceback.print_exc()
                input("\nPress Enter to exit...")
                return 1
            # Retry import after install
            continue
        except Exception as e:
            try:
                logger.exception("Failed to start PDF Search GUI.")
            except Exception:
                pass
            # Fail loudly but cleanly
            print("Failed to start PDF Search GUI.", file=sys.stderr)
            print(str(e), file=sys.stderr)
            traceback.print_exc()
            input("\nPress Enter to exit...")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
