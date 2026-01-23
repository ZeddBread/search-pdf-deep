# PDF Search (Deep)

A powerful Python application for searching text within PDF files across entire folder structures. Supports both graphical and command-line interfaces, with advanced features including regex matching, OCR for scanned documents, and multiprocessing for fast searches.

## Purpose

PDF Search (Deep) helps you quickly find specific text or patterns across multiple PDF files in a directory. Whether you're searching through a collection of documents, invoices, reports, or any PDF-based archive, this tool provides fast and accurate text matching with support for scanned/image-based PDFs through OCR.

## Features

- **Dual Interface**: Modern GUI built with CustomTkinter and a command-line interface for automation
- **Text & Regex Search**: Search for literal text or use regular expressions for pattern matching
- **Case-Insensitive Matching**: Optional case-insensitive search for flexible queries
- **Recursive Folder Search**: Search through subdirectories automatically
- **OCR Support**: Automatically detects and processes scanned/image-based PDFs using Tesseract OCR
- **Configurable OCR Quality**: Adjustable DPI settings for OCR processing
- **Multiprocessing**: Parallel processing for faster searches across large PDF collections
- **Progress Tracking**: Real-time progress updates and match counts
- **Result Management**: 
  - Double-click to open PDFs at the matching page
  - Export results to CSV
  - Copy file paths to clipboard
  - Open containing folders
- **Settings Persistence**: Remembers your preferences (folder, options, window size)
- **Snippet Preview**: Shows context around each match for quick verification

## How to Run

### Prerequisites

- Python 3.7 or higher
- Tesseract OCR (optional, only needed for OCR functionality)
  - Windows: Download from [GitHub Tesseract releases](https://github.com/UB-Mannheim/tesseract/wiki)
  - macOS: `brew install tesseract`
  - Linux: `sudo apt-get install tesseract-ocr` (Ubuntu/Debian) or equivalent

### Quick Start (GUI - Recommended)

The easiest way to run the application:

```bash
python run_pdf_search.py
```

The launcher will automatically install missing dependencies if needed.

### Manual Installation

If you prefer to install dependencies manually:

**Using pip:**
```bash
pip install -r requirements.txt
python run_pdf_search.py
```

**Using uv:**
```bash
uv pip install -r requirements.txt
python run_pdf_search.py
```

### Command-Line Interface

For automation or scripted searches:

```bash
# Basic search
python pdf_search_cli.py "C:\Docs\PDFs" "provider number" --ignore-case --recursive

# Regex search
python pdf_search_cli.py "C:\Docs\PDFs" "HPI-I\s*:\s*\d+" --regex --recursive

# With OCR for scanned PDFs
python pdf_search_cli.py "C:\Docs\PDFs" "signature" --include-ocr --recursive --ocr-dpi 300
```

**CLI Options:**
- `--regex`: Treat query as a regular expression
- `--ignore-case`: Case-insensitive matching
- `--recursive`: Search subfolders
- `--include-ocr`: Enable OCR for scanned pages (slower)
- `--ocr-dpi`: OCR render DPI (default: 200)

### GUI Usage

1. **Select Folder**: Click "Browse" to choose the folder containing your PDFs
2. **Enter Search Query**: Type the text or regex pattern you want to find
3. **Configure Options**:
   - **Regex**: Enable to use regular expressions
   - **Ignore case**: Case-insensitive search
   - **Recursive**: Search subfolders
   - **OCR scanned pages**: Enable OCR for image-based PDFs
   - **OCR DPI**: Set the quality/resolution for OCR processing
4. **Search**: Click "Search" to start (or press Enter in the search field)
5. **View Results**: 
   - Double-click any result to open the PDF at that page
   - Use toolbar buttons to open files/folders, copy paths, or export to CSV

## Dependencies

- `pymupdf` - PDF text extraction
- `customtkinter` - Modern GUI framework
- `pillow` - Image processing for OCR
- `pytesseract` - Python wrapper for Tesseract OCR
