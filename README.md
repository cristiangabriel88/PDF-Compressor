# PDF Compressor

A small Windows desktop app that shrinks PDF files toward a target size while
keeping them printable. Text and vector graphics are never rasterized — only
embedded raster images are downsampled / re-encoded, and never below a
print-safe DPI floor.

## Features

- Drag and drop PDFs into a table (name, path, current size).
- Per-file editable **Target (KB)** column — double-click the cell to set it.
- One big **COMPRESS** button.
- Compressed copies are saved next to the originals as `<name>_compressed.pdf`.
  The original files are never modified.
- If a target can't be reached without dropping below print quality, the app
  keeps the smallest safe result and marks the row as *Best effort*.

## How compression works

1. **Lossless pass** — stream/object optimization and garbage collection
   (`pikepdf` + `PyMuPDF`). If that already meets the target, it stops here.
2. **Image recompression** — if still too big, embedded images are downsampled
   and re-encoded as JPEG, trying progressively more aggressive settings
   (300 DPI down to a 150 DPI / quality-60 floor) until the target is met.
3. **Best effort** — if even the floor settings don't reach the target, the
   smallest valid result is kept and the row is flagged.

## Run from source

```bat
pip install -r requirements.txt
python main.py
```

## Build the .exe

```bat
build.bat
```

This produces a single self-contained `dist\PDFCompressor.exe` that runs on any
Windows PC with no Python install required.
