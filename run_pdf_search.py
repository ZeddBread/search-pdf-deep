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
    # Try to launch; if a dependency is missing, auto-install and retry once.
    attempts = 0
    while True:
        try:
            from pdf_search_gui import main as gui_main

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
            print(f"Missing dependency: {missing!r}. Installing requirements...", file=sys.stderr)
            try:
                _install_missing_module(missing)
            except Exception as install_err:
                print("Auto-install failed.", file=sys.stderr)
                print(str(install_err), file=sys.stderr)
                traceback.print_exc()
                input("\nPress Enter to exit...")
                return 1
            # Retry import after install
            continue
        except Exception as e:
            # Fail loudly but cleanly
            print("Failed to start PDF Search GUI.", file=sys.stderr)
            print(str(e), file=sys.stderr)
            traceback.print_exc()
            input("\nPress Enter to exit...")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
