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


class CompressionAborted(Exception):
    """Raised when ``should_stop`` returns truthy mid-compression."""


@dataclass
class CompressResult:
    output_path: str
    final_bytes: int
    target_met: bool
    method: str  # "lossless" | "image-recompress" | "best-effort" | "copy"
    message: str


@dataclass
class _ImageCandidate:
    xref: int
    pil: Image.Image  # decoded once, reused for every grid pass
    src_w: int
    src_h: int
    disp_w: float
    disp_h: float
    original_bytes: int


def _kb(n):
    return f"{n / 1024:.0f} KB"


def _size(path):
    return os.path.getsize(path)


def _finalize(src, dst):
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst)


def _lossless_pikepdf(src, dst):
    # recompress_flate=True forces every flate stream to be decompressed
    # and re-deflated at max effort -- the main source of slowness on PDFs
    # with many small streams. Skipping it loses only marginal size.
    with pikepdf.open(src) as pdf:
        pdf.save(
            dst,
            compress_streams=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            linearize=False,
        )


def _lossless_mupdf(src, dst):
    # clean=True re-parses every page's content stream and was the slow
    # path on content-heavy PDFs; deflate + garbage gets most of the win.
    doc = fitz.open(src)
    try:
        doc.save(dst, garbage=4, deflate=True)
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


def _scan_image_candidates(src):
    """One-time scan: identify and decode every eligible image.

    The decoded PIL bitmaps are reused for each grid pass, which avoids
    re-extracting and re-decoding the same images 7 times.
    """
    candidates = []
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
                if pil.mode not in ("RGB", "L"):
                    try:
                        pil = pil.convert("RGB")
                    except Exception:
                        continue
                disp = display.get(xref, (0.0, 0.0))
                candidates.append(_ImageCandidate(
                    xref=xref, pil=pil,
                    src_w=pil.width, src_h=pil.height,
                    disp_w=disp[0], disp_h=disp[1],
                    original_bytes=len(raw),
                ))
    finally:
        doc.close()
    return candidates


def _recompress_with_candidates(src, dst, candidates_by_xref, dpi, quality):
    """Re-encode cached candidates at given dpi/quality, then save the doc.

    Uses ``garbage=3, deflate=True`` (no ``clean=True``) for the intermediate
    save -- ``clean=True`` re-parses every page's content stream which is the
    main reason the old per-pass implementation was slow.
    """
    doc = fitz.open(src)
    try:
        seen = set()
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                c = candidates_by_xref.get(xref)
                if c is None:
                    continue

                if c.disp_w > 0 and c.disp_h > 0:
                    max_w = max(1, int(dpi * c.disp_w / 72.0))
                    max_h = max(1, int(dpi * c.disp_h / 72.0))
                else:
                    max_w, max_h = c.src_w, c.src_h
                new_w, new_h = min(c.src_w, max_w), min(c.src_h, max_h)

                pil = c.pil
                if (new_w, new_h) != (pil.width, pil.height):
                    pil = pil.resize((new_w, new_h), _RESAMPLE)

                buf = io.BytesIO()
                try:
                    pil.save(buf, format="JPEG", quality=quality)
                except Exception:
                    continue
                new_bytes = buf.getvalue()
                if len(new_bytes) >= c.original_bytes:
                    continue

                try:
                    page.replace_image(xref, stream=new_bytes)
                except Exception:
                    continue

        doc.save(dst, garbage=3, deflate=True)
    finally:
        doc.close()


def compress_pdf(input_path, output_path, target_bytes=None,
                 min_dpi=150, min_jpeg_quality=60, progress_cb=None,
                 should_stop=None):
    """Compress ``input_path``, writing ``output_path``.

    If ``target_bytes`` is given, compression stops as soon as the file is at
    or below it. If ``target_bytes`` is ``None``, the file is compressed as
    much as possible while staying within the print-safe quality floor.

    ``should_stop`` may be a callable returning truthy to request an early
    abort. It is polled at phase boundaries; on abort, :class:`CompressionAborted`
    is raised and no output is written.

    Returns a :class:`CompressResult`. The original file is never modified.
    """
    def report(msg):
        if progress_cb:
            progress_cb(msg)

    def check_stop():
        if should_stop and should_stop():
            raise CompressionAborted()

    maximal = target_bytes is None
    original = _size(input_path)
    tmpdir = tempfile.mkdtemp(prefix="pdfcomp_")
    try:
        # --- Step 1: lossless optimization -----------------------------------
        check_stop()
        report("Lossless optimization...")
        best_path, best_size, best_method = input_path, original, "copy"
        for idx, fn in enumerate((_lossless_pikepdf, _lossless_mupdf)):
            check_stop()
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

        # --- Step 2: pre-scan, then iterative image recompression -----------
        check_stop()
        report("Analyzing images...")
        try:
            candidates = _scan_image_candidates(input_path)
        except Exception:
            candidates = []

        if candidates:
            candidates_by_xref = {c.xref: c for c in candidates}
            grid = [(d, q) for (d, q) in SEARCH_GRID
                    if d >= min_dpi and q >= min_jpeg_quality]
            prev_size = None
            for dpi, quality in grid:
                check_stop()
                report(f"Recompressing images at {dpi} DPI, quality {quality}...")
                tmp = os.path.join(tmpdir, f"img_{dpi}_{quality}.pdf")
                try:
                    _recompress_with_candidates(
                        input_path, tmp, candidates_by_xref, dpi, quality)
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
                # Maximal mode: stop once size stops improving.
                if maximal and prev_size is not None and s >= prev_size:
                    break
                prev_size = s

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
            f"(best effort, target {_kb(target_bytes)})",
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
