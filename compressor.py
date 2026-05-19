"""Pure-Python PDF compression engine.

Shrinks a PDF toward a target byte size while preserving printability:
text and vector art are never rasterized, only embedded raster images are
downsampled / re-encoded, and never below a print-safe DPI / quality floor.
"""

import io
import os
import shutil
import tempfile
from dataclasses import dataclass

import fitz  # PyMuPDF
import pikepdf
from PIL import Image

try:
    _RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:  # Pillow < 9.1
    _RESAMPLE = Image.LANCZOS

# (dpi, jpeg_quality) tried from gentlest to most aggressive.
SEARCH_GRID = [
    (300, 85),
    (250, 82),
    (225, 80),
    (200, 75),
    (175, 72),
    (150, 70),
    (150, 60),
]

# Images smaller than this (encoded) are left untouched -- not worth the risk.
MIN_IMAGE_BYTES = 30 * 1024


@dataclass
class CompressResult:
    output_path: str
    final_bytes: int
    target_met: bool
    method: str  # "lossless" | "image-recompress" | "best-effort" | "copy"
    message: str


def _kb(n):
    return f"{n / 1024:.0f} KB"


def _size(path):
    return os.path.getsize(path)


def _finalize(src, dst):
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst)


def _lossless_pikepdf(src, dst):
    with pikepdf.open(src) as pdf:
        pdf.save(
            dst,
            compress_streams=True,
            recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            linearize=False,
        )


def _lossless_mupdf(src, dst):
    doc = fitz.open(src)
    try:
        doc.save(dst, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


def _xref_max_display_size(doc):
    """Largest on-page rectangle (in points) each image xref is drawn at."""
    sizes = {}
    for page in doc:
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = []
            for r in rects:
                cur = sizes.get(xref, (0.0, 0.0))
                sizes[xref] = (max(cur[0], r.width), max(cur[1], r.height))
    return sizes


def _recompress_images(src, dst, dpi, quality):
    """Downsample/re-encode raster images, then save with garbage collection."""
    doc = fitz.open(src)
    try:
        display = _xref_max_display_size(doc)
        seen = set()
        for page in doc:
            for img in page.get_images(full=True):
                xref, smask = img[0], img[1]
                if xref in seen:
                    continue
                seen.add(xref)
                if smask != 0:
                    continue  # soft-masked / transparent -- leave alone

                try:
                    info = doc.extract_image(xref)
                except Exception:
                    continue
                raw = info.get("image")
                if not raw or len(raw) < MIN_IMAGE_BYTES:
                    continue

                try:
                    pil = Image.open(io.BytesIO(raw))
                    pil.load()
                except Exception:
                    continue
                if pil.mode in ("RGBA", "LA", "PA"):
                    continue
                if pil.mode == "P" and "transparency" in pil.info:
                    continue

                src_w, src_h = pil.width, pil.height
                disp = display.get(xref)
                if disp and disp[0] > 0 and disp[1] > 0:
                    max_w = max(1, int(dpi * disp[0] / 72.0))
                    max_h = max(1, int(dpi * disp[1] / 72.0))
                else:
                    max_w, max_h = src_w, src_h
                new_w, new_h = min(src_w, max_w), min(src_h, max_h)

                if pil.mode not in ("RGB", "L"):
                    try:
                        pil = pil.convert("RGB")
                    except Exception:
                        continue
                if (new_w, new_h) != (src_w, src_h):
                    pil = pil.resize((new_w, new_h), _RESAMPLE)

                buf = io.BytesIO()
                try:
                    pil.save(buf, format="JPEG", quality=quality, optimize=True)
                except Exception:
                    continue
                new_bytes = buf.getvalue()
                if len(new_bytes) >= len(raw):
                    continue  # recompression didn't help this image

                try:
                    page.replace_image(xref, stream=new_bytes)
                except Exception:
                    continue

        doc.save(dst, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


def compress_pdf(input_path, output_path, target_bytes=None,
                 min_dpi=150, min_jpeg_quality=60, progress_cb=None):
    """Compress ``input_path``, writing ``output_path``.

    If ``target_bytes`` is given, compression stops as soon as the file is at
    or below it. If ``target_bytes`` is ``None``, the file is compressed as
    much as possible while staying within the print-safe quality floor.

    Returns a :class:`CompressResult`. The original file is never modified.
    """
    def report(msg):
        if progress_cb:
            progress_cb(msg)

    maximal = target_bytes is None
    original = _size(input_path)
    tmpdir = tempfile.mkdtemp(prefix="pdfcomp_")
    try:
        # --- Step 1: lossless optimization -----------------------------------
        report("Optimizare fără pierderi...")
        best_path, best_size, best_method = input_path, original, "copy"
        for idx, fn in enumerate((_lossless_pikepdf, _lossless_mupdf)):
            tmp = os.path.join(tmpdir, f"lossless_{idx}.pdf")
            try:
                fn(input_path, tmp)
            except Exception:
                continue
            if os.path.exists(tmp):
                s = _size(tmp)
                if s < best_size:
                    best_path, best_size, best_method = tmp, s, "lossless"

        if not maximal and best_size <= target_bytes:
            _finalize(best_path, output_path)
            final = _size(output_path)
            return CompressResult(
                output_path, final, True, best_method,
                f"{_kb(original)} → {_kb(final)}",
            )

        # --- Step 2: iterative image recompression ---------------------------
        grid = [(d, q) for (d, q) in SEARCH_GRID
                if d >= min_dpi and q >= min_jpeg_quality]
        for dpi, quality in grid:
            report(f"Recomprimare imagini la {dpi} DPI, calitate {quality}...")
            tmp = os.path.join(tmpdir, f"img_{dpi}_{quality}.pdf")
            try:
                _recompress_images(input_path, tmp, dpi, quality)
            except Exception:
                continue
            if not os.path.exists(tmp):
                continue
            s = _size(tmp)
            if s < best_size:
                best_path, best_size, best_method = tmp, s, "image-recompress"
            if not maximal and s <= target_bytes:
                _finalize(best_path, output_path)
                final = _size(output_path)
                return CompressResult(
                    output_path, final, True, "image-recompress",
                    f"{_kb(original)} → {_kb(final)}",
                )

        # --- Step 3: best-effort fallback ------------------------------------
        _finalize(best_path, output_path)
        final = _size(output_path)
        if maximal:
            return CompressResult(
                output_path, final, True, best_method,
                f"{_kb(original)} → {_kb(final)}",
            )
        met = final <= target_bytes
        return CompressResult(
            output_path, final, met,
            best_method if met else "best-effort",
            f"{_kb(original)} → {_kb(final)} "
            f"(minim posibil, țintă {_kb(target_bytes)})",
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
