# PDF Compressor

A desktop application for compressing PDF files without rasterizing text or vector content. Drag and drop one or more PDFs, click **Compress**, and receive smaller copies written alongside the originals — the source files are never touched.

Available in **English** and **Romanian** (switchable at runtime from the language selector in the top bar).

---

## Features

- **Drag-and-drop** or click-to-browse file loading
- **Lossless pass** first — stream re-compression via pikepdf + MuPDF garbage collection
- **Image recompression** — embedded rasters are downsampled and JPEG-encoded at progressively lower DPI/quality until size stops improving, while staying within a print-safe floor (150 DPI / quality 60)
- Text and vector art are **never rasterized**
- Transparent/alpha images are left untouched to avoid artefacts
- **Custom output folder** — or save next to each original (default)
- **Multi-file queue** with per-file status, input/output sizes, and a progress bar
- Elapsed time shown during compression
- EN / RO language selector in the header bar
- Light theme (Sun Valley TTK)

---

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`:

```
PyMuPDF>=1.23
pikepdf>=8
Pillow>=10
tkinterdnd2>=0.4
sv-ttk>=2.6
pyinstaller>=6   # only needed to build the .exe
```

Install with:

```bash
pip install -r requirements.txt
```

---

## Running from source

```bash
python main.py
```

Or double-click `run.bat` on Windows.

---

## Building a standalone executable

Run `build.bat` (Windows) or invoke PyInstaller directly:

```bash
python -m PyInstaller PDFCompressor.spec --noconfirm
```

The output is placed in `dist\PDFCompressor\`. To distribute, zip the entire `dist\PDFCompressor\` folder.

---

## How compression works

1. **Lossless optimisation** — the PDF is saved twice (once with pikepdf, once with MuPDF) with stream recompression and cross-reference/object-stream compaction. The smaller result is kept.
2. **Image recompression** — embedded raster images larger than 30 KB are downsampled to the DPI they are actually displayed at (so a 600 DPI scan shown at 150 DPI points is downsampled to 150 DPI) and re-encoded as JPEG. Seven DPI/quality combinations are tried from gentlest to most aggressive; the smallest result that stays above the print-safe floor is kept.
3. The smallest output from all passes is written to disk. The original is never modified.

---

## Project structure

| File | Purpose |
|------|---------|
| `main.py` | Tkinter UI, drag-and-drop, language switching |
| `compressor.py` | Pure compression engine (no UI dependency) |
| `PDFCompressor.spec` | PyInstaller build spec |
| `build.bat` | One-click build script |
| `run.bat` | One-click run-from-source script |
| `icon.ico` / `icon.png` | Application icon |

---

## License

2026
