# PDF Search (Deep)

Search a folder of PDFs for text (with optional regex, recursion, and OCR for scanned pages). Includes a simple GUI and a CLI.

## How to run

### Option A: Run the GUI (recommended)

```bash
python run_pdf_search.py
```

### Option B: Install dependencies first (then run the GUI)

Using pip:

```bash
python -m pip install -r requirements.txt
python run_pdf_search.py
```

Using uv (if you use it):

```bash
uv pip install -r requirements.txt
python run_pdf_search.py
```

## How to use (GUI)

- **Folder**: click **Browse** and pick the folder that contains your PDFs.
- **Search**: type the text (or regex) you want to find, then click **Search**.
- **Options**:
  - **Regex**: interpret the search text as a regular expression.
  - **Ignore case**: case-insensitive matching.
  - **Recursive**: search subfolders.
  - **OCR scanned pages (slow)** + **OCR DPI**: enables OCR for image-only PDFs.
- **Results**:
  - **Double-click** a result (or use **Open File**) to open the PDF.
  - Use **Open Folder** to open the containing folder.
  - Use **Copy Path** to copy the full file path.
  - Use **Export CSV** to export all results.

## CLI examples

```bash
python pdf_search.py "C:\Docs\PDFs" "provider number" --ignore-case --recursive
python pdf_search.py "C:\Docs\PDFs" "HPI-I\s*:\s*\d+" --regex --recursive
python pdf_search.py "C:\Docs\PDFs" "signature" --include-ocr --recursive
```
