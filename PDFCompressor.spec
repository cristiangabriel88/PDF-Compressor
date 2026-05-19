# PyInstaller spec for PDF Compressor.
# One-folder build: starts instantly (no temp extraction) and is far less
# likely to be blocked by antivirus / SmartScreen than a one-file exe.
# Output: dist\PDFCompressor\PDFCompressor.exe  (ship the whole folder).
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("tkinterdnd2", "pikepdf", "fitz", "sv_ttk"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += [("icon.ico", ".")]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PDFCompressor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon="icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PDFCompressor",
)
