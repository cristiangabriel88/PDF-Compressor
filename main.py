"""PDF Compressor -- drag-and-drop desktop app (Romanian UI).

Drop PDFs into the table and click Compress. Each file is compressed as much
as possible while staying printable. Compressed copies are written next to the
originals as ``<name>_compressed.pdf``; the originals are never modified.
"""

import os
import sys
import threading
import time
from tkinter import ttk, messagebox, filedialog

import sv_ttk
from tkinterdnd2 import DND_FILES, TkinterDnD

from compressor import compress_pdf

COLUMNS = ("name", "path", "current", "result", "status")
HEADINGS = {
    "name": "Nume",
    "path": "Cale",
    "current": "Dimensiune actuală",
    "result": "Rezultat",
    "status": "Stare",
}
COL_WIDTHS = {
    "name": 220,
    "path": 360,
    "current": 130,
    "result": 110,
    "status": 240,
}

ACCENT = "#0067c0"
OK_COLOR = "#107c10"
WARN_COLOR = "#9d5d00"
ERR_COLOR = "#c42b1c"
MUTED = "#5d5d5d"

# compress_pdf reports this many progress steps per file (1 lossless pass +
# 7 image-recompression grid steps) -- used to animate the progress bar.
STEPS_PER_FILE = 8


def resource_path(name):
    """Path to a bundled resource, working both from source and frozen exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def fmt_kb(num_bytes):
    return f"{num_bytes / 1024:,.0f} KB"


def fmt_duration(seconds):
    seconds = max(0, int(round(seconds)))
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def unique_output_path(input_path, output_dir=None):
    folder = output_dir if output_dir else os.path.dirname(input_path)
    stem = os.path.splitext(os.path.basename(input_path))[0]
    candidate = os.path.join(folder, f"{stem}_compressed.pdf")
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{stem}_compressed ({n}).pdf")
        n += 1
    return candidate


class PdfCompressorApp:
    def __init__(self, root):
        self.root = root
        self.rows = {}  # item_id -> {"path", "size"}
        self.compressing = False
        self.output_dir = None  # None -> save next to each original
        self.start_time = None

        root.title("Compresor PDF")
        root.geometry("1100x640")
        root.minsize(900, 480)
        try:
            root.iconbitmap(default=resource_path("icon.ico"))
        except Exception:
            pass

        sv_ttk.set_theme("light")
        self._apply_styles()

        self._build_appfooter(root)

        container = ttk.Frame(root, padding=20)
        container.pack(fill="both", expand=True)

        self._build_header(container)
        self._build_table(container)
        self._build_controls(container)
        self._build_progress(container)
        self._wire_dnd()

    # ----- styling --------------------------------------------------------
    def _apply_styles(self):
        style = ttk.Style()
        style.configure("Treeview", rowheight=34, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10),
                        padding=(8, 6))
        # large pill-shaped primary action button (inherits sv-ttk Accent)
        style.configure("Big.Accent.TButton",
                        font=("Segoe UI Semibold", 13), padding=(28, 14))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 18))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10),
                        foreground=MUTED)
        style.configure("Footer.TLabel", font=("Segoe UI", 10),
                        foreground=MUTED)
        style.configure("AppFooter.TLabel", font=("Segoe UI", 9),
                        foreground=MUTED)
        style.configure("Card.TFrame", relief="flat")

    # ----- layout ---------------------------------------------------------
    def _build_appfooter(self, parent):
        footer = ttk.Frame(parent, padding=(20, 7))
        footer.pack(side="bottom", fill="x")
        ttk.Separator(parent, orient="horizontal").pack(side="bottom", fill="x")
        ttk.Label(footer, text="2026   ·   Versiunea 1.0   ·   CNARNN-INFONOT",
                  style="AppFooter.TLabel").pack(side="right")

    def _build_header(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill="x", pady=(0, 16))
        ttk.Label(header, text="Compresor PDF",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Trageți și plasați fișiere PDF mai jos, apoi apăsați "
                 "Comprimare. Fișierele originale nu sunt modificate niciodată.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

    def _build_table(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="both", expand=True)

        table_frame = ttk.Frame(card)
        table_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            table_frame, columns=COLUMNS, show="headings",
            selectmode="extended",
        )
        for col in COLUMNS:
            self.tree.heading(col, text=HEADINGS[col])
            anchor = "w" if col in ("name", "path") else "center"
            self.tree.column(col, width=COL_WIDTHS[col], anchor=anchor,
                             stretch=(col in ("path", "status")))

        vsb = ttk.Scrollbar(table_frame, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.tree.tag_configure("done", foreground=OK_COLOR)
        self.tree.tag_configure("besteffort", foreground=WARN_COLOR)
        self.tree.tag_configure("error", foreground=ERR_COLOR)
        self.tree.tag_configure("odd", background="#fafafa")

        self.tree.bind("<Delete>", lambda e: self._remove_selected())
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Button-1>", self._on_tree_click, add="+")

        # empty-state placeholder shown over the table when no files loaded
        self.placeholder = ttk.Label(
            table_frame,
            text="⊕   Plasați fișierele PDF aici  ·  sau faceți click pentru a răsfoi",
            font=("Segoe UI", 13), foreground=MUTED, anchor="center",
            cursor="hand2",
        )
        self.placeholder.bind("<Button-1>", self._browse_files)
        self._show_placeholder()

    def _build_controls(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(16, 0))

        ttk.Button(bar, text="Șterge tot",
                   command=self._clear_all).pack(side="left")
        ttk.Button(bar, text="Elimină selecția",
                   command=self._remove_selected).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Folder destinație…",
                   command=self._choose_output_dir).pack(side="left", padx=(8, 0))

        self.output_label = ttk.Label(bar, style="Footer.TLabel")
        self.output_label.pack(side="left", padx=(12, 0))
        self.output_label.bind("<Button-1>", lambda e: self._reset_output_dir())
        self._update_output_label()

        self.footer = ttk.Label(bar, text="Niciun fișier încărcat.",
                                style="Footer.TLabel")
        self.footer.pack(side="left", padx=16)

        self.compress_btn = ttk.Button(
            bar, text="Comprimare", style="Big.Accent.TButton",
            command=self._start_compression,
        )
        self.compress_btn.pack(side="right")

    def _build_progress(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(14, 0))
        top = ttk.Frame(bar)
        top.pack(fill="x", pady=(0, 5))
        self.progress_label = ttk.Label(top, text="Pregătit",
                                        style="Footer.TLabel")
        self.progress_label.pack(side="left", anchor="w")
        self.time_label = ttk.Label(top, text="", style="Footer.TLabel")
        self.time_label.pack(side="right", anchor="e")
        self.progress = ttk.Progressbar(bar, mode="determinate", maximum=1)
        self.progress.pack(fill="x")

    def _wire_dnd(self):
        for widget in (self.tree, self.placeholder):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)

    # ----- progress bar ---------------------------------------------------
    def _progress_begin_file(self, name, idx, total):
        self.progress["value"] = idx - 1
        self.progress_label.config(
            text=f"Se comprimă {name}  ({idx}/{total})…")

    def _progress_step(self, name, idx, total, step, msg):
        self.progress["value"] = (idx - 1) + min(step / STEPS_PER_FILE, 1.0)
        self.progress_label.config(text=f"{name}  ({idx}/{total})  —  {msg}")

    def _progress_finish_file(self, idx):
        self.progress["value"] = idx

    def _tick(self):
        """Update elapsed / remaining time once a second while compressing."""
        if not self.compressing or self.start_time is None:
            return
        elapsed = time.monotonic() - self.start_time
        frac = 0.0
        maximum = float(self.progress["maximum"])
        if maximum > 0:
            frac = float(self.progress["value"]) / maximum
        if frac > 0.02:
            remaining = elapsed / frac * (1.0 - frac)
            self.time_label.config(
                text=f"Timp: {fmt_duration(elapsed)}   ·   "
                     f"Rămas: ~{fmt_duration(remaining)}")
        else:
            self.time_label.config(
                text=f"Timp: {fmt_duration(elapsed)}   ·   "
                     f"Rămas: se estimează…")
        self.root.after(1000, self._tick)

    # ----- empty-state placeholder ---------------------------------------
    def _show_placeholder(self):
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _hide_placeholder(self):
        self.placeholder.place_forget()

    # ----- file management ------------------------------------------------
    def _add_paths(self, paths):
        added = 0
        for raw in paths:
            if self._add_file(raw):
                added += 1
        if added:
            self._update_footer()

    def _on_drop(self, event):
        self._add_paths(self.root.tk.splitlist(event.data))

    def _on_tree_click(self, event):
        # clicking empty space (not a row) acts as the drop zone
        if not self.compressing and not self.tree.identify_row(event.y):
            self._browse_files()

    def _browse_files(self, event=None):
        if self.compressing:
            return
        paths = filedialog.askopenfilenames(
            title="Selectați fișiere PDF",
            filetypes=[("Fișiere PDF", "*.pdf"), ("Toate fișierele", "*.*")],
        )
        if paths:
            self._add_paths(paths)

    # ----- output folder --------------------------------------------------
    def _choose_output_dir(self):
        if self.compressing:
            return
        folder = filedialog.askdirectory(
            title="Alegeți unde să salvați fișierele PDF comprimate")
        if folder:
            self.output_dir = os.path.abspath(folder)
            self._update_output_label()

    def _reset_output_dir(self):
        if self.compressing or self.output_dir is None:
            return
        self.output_dir = None
        self._update_output_label()

    def _update_output_label(self):
        if self.output_dir:
            disp = self.output_dir
            parts = disp.split(os.sep)
            if len(parts) > 3:
                disp = "…" + os.sep + os.sep.join(parts[-2:])
            self.output_label.config(
                text=f"Salvare în: {disp}   (clic pentru resetare)",
                cursor="hand2")
        else:
            self.output_label.config(
                text="Salvare lângă fiecare fișier original - ", cursor="")

    def _add_file(self, path):
        path = os.path.abspath(path)
        if not path.lower().endswith(".pdf") or not os.path.isfile(path):
            return False
        if any(r["path"] == path for r in self.rows.values()):
            return False
        try:
            size = os.path.getsize(path)
        except OSError:
            return False
        item = self.tree.insert(
            "", "end",
            values=(os.path.basename(path), path, fmt_kb(size), "",
                    "Pregătit"),
        )
        self.rows[item] = {"path": path, "size": size}
        self._restripe()
        self._hide_placeholder()
        return True

    def _restripe(self):
        for idx, item in enumerate(self.tree.get_children()):
            current = [t for t in self.tree.item(item, "tags")
                       if t != "odd"]
            if idx % 2:
                current.append("odd")
            self.tree.item(item, tags=tuple(current))

    def _remove_selected(self):
        if self.compressing:
            return
        for item in self.tree.selection():
            self.tree.delete(item)
            self.rows.pop(item, None)
        self._restripe()
        if not self.rows:
            self._show_placeholder()
        self._update_footer()

    def _clear_all(self):
        if self.compressing:
            return
        for item in list(self.rows):
            self.tree.delete(item)
        self.rows.clear()
        self._show_placeholder()
        self._update_footer()

    def _on_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self._remove_selected()

    def _update_footer(self, extra=""):
        n = len(self.rows)
        if n == 0:
            base = "Niciun fișier încărcat."
        elif n == 1:
            base = "1 fișier încărcat."
        else:
            base = f"{n} fișiere încărcate."
        self.footer.config(text=f"{base}  {extra}".strip())

    # ----- compression ----------------------------------------------------
    def _set_cell(self, item, column, text):
        if item not in self.rows:
            return
        values = list(self.tree.item(item, "values"))
        values[COLUMNS.index(column)] = text
        self.tree.item(item, values=values)

    def _set_status_tag(self, item, tag):
        keep = [t for t in self.tree.item(item, "tags") if t == "odd"]
        if tag:
            keep.append(tag)
        self.tree.item(item, tags=tuple(keep))

    def _ui(self, fn, *args):
        self.root.after(0, lambda: fn(*args))

    def _start_compression(self):
        if self.compressing:
            return
        if not self.rows:
            messagebox.showinfo("Compresor PDF",
                                "Adăugați mai întâi fișiere PDF.")
            return
        self.compressing = True
        self.start_time = time.monotonic()
        self.compress_btn.config(state="disabled", text="Se comprimă…")
        total = len(self.rows)
        self.progress.config(maximum=total, value=0)
        self.progress_label.config(text=f"Se pregătește…  (0/{total})")
        self.time_label.config(text="Timp: 0:00   ·   Rămas: se estimează…")
        self._tick()
        for item in self.rows:
            self._set_cell(item, "result", "")
            self._set_cell(item, "status", "În așteptare")
            self._set_status_tag(item, None)
        snapshot = [(item, dict(data)) for item, data in self.rows.items()]
        threading.Thread(target=self._worker, args=(snapshot, self.output_dir),
                         daemon=True).start()

    def _worker(self, snapshot, out_dir):
        total = len(snapshot)
        errors = 0
        for idx, (item, data) in enumerate(snapshot, start=1):
            name = os.path.basename(data["path"])
            self._ui(self._set_cell, item, "status", "Se comprimă…")
            self._ui(self._progress_begin_file, name, idx, total)
            step_count = [0]

            def progress(msg, _item=item, _name=name, _idx=idx):
                step_count[0] += 1
                self._ui(self._set_cell, _item, "status", msg)
                self._ui(self._progress_step, _name, _idx, total,
                         step_count[0], msg)

            try:
                out_path = unique_output_path(data["path"], out_dir)
                result = compress_pdf(data["path"], out_path,
                                      progress_cb=progress)
                self._ui(self._apply_result, item, result)
            except Exception as exc:  # noqa: BLE001 - surface any failure in-row
                errors += 1
                self._ui(self._apply_error, item, str(exc))
            self._ui(self._progress_finish_file, idx)
        self._ui(self._finish_compression, total, errors)

    def _apply_result(self, item, result):
        if item not in self.rows:
            return
        self._set_cell(item, "result", fmt_kb(result.final_bytes))
        self._set_cell(item, "status", f"Gata  —  {result.message}")
        self._set_status_tag(item, "done")

    def _apply_error(self, item, message):
        if item not in self.rows:
            return
        self._set_cell(item, "result", "—")
        self._set_cell(item, "status", f"Eroare: {message}")
        self._set_status_tag(item, "error")

    def _finish_compression(self, total=0, errors=0):
        self.compressing = False
        self.compress_btn.config(state="normal", text="Comprimare")
        self.progress["value"] = self.progress["maximum"]
        if self.start_time is not None:
            elapsed = time.monotonic() - self.start_time
            self.time_label.config(
                text=f"Timp total: {fmt_duration(elapsed)}")
        if errors:
            ok = total - errors
            self.progress_label.config(
                text=f"Gata  —  {ok} reușite, {errors} cu erori din {total}")
        elif total == 1:
            self.progress_label.config(text="Gata  —  1 fișier comprimat")
        else:
            self.progress_label.config(
                text=f"Gata  —  {total} fișiere comprimate")


def main():
    root = TkinterDnD.Tk()
    PdfCompressorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
