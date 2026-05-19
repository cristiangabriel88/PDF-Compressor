"""PDF Compressor -- drag-and-drop desktop app with EN/RO language support."""

import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import sv_ttk
from tkinterdnd2 import DND_FILES, TkinterDnD

from compressor import compress_pdf

COLUMNS = ("name", "path", "current", "result", "status")

ACCENT = "#0067c0"
OK_COLOR = "#107c10"
WARN_COLOR = "#9d5d00"
ERR_COLOR = "#c42b1c"
MUTED = "#5d5d5d"

# compress_pdf reports this many progress steps per file (1 lossless pass +
# 7 image-recompression grid steps) -- used to animate the progress bar.
STEPS_PER_FILE = 8

STRINGS = {
    "en": {
        "app_title": "PDF Compressor",
        "subtitle": "Drag and drop PDF files below, then click Compress. Original files are never modified.",
        "footer_brand": "2026   ·   Version 1.0",
        "placeholder": "⊕   Drop PDF files here  ·  or click to browse",
        "btn_clear_all": "Clear all",
        "btn_remove_selected": "Remove selected",
        "btn_output_dir": "Output folder…",
        "btn_compress": "Compress",
        "btn_compressing": "Compressing…",
        "col_name": "Name",
        "col_path": "Path",
        "col_current": "Current size",
        "col_result": "Result",
        "col_status": "Status",
        "no_files": "No files loaded.",
        "n_files_1": "1 file loaded.",
        "n_files_n": "{n} files loaded.",
        "save_next_to": "Save next to each original file",
        "save_in": "Save in: {path}   (click to reset)",
        "ready": "Ready",
        "time_elapsed": "Elapsed: {t}",
        "preparing": "Preparing…  (0/{total})",
        "compressing_file": "Compressing {name}  ({idx}/{total})…",
        "step_progress": "{name}  ({idx}/{total})  —  {msg}",
        "waiting": "Waiting",
        "compressing": "Compressing…",
        "done_result": "Done  —  {msg}",
        "error_result": "Error: {msg}",
        "total_time": "Total time: {t}",
        "done_1": "Done  —  1 file compressed",
        "done_n": "Done  —  {total} files compressed",
        "done_errors": "Done  —  {ok} succeeded, {errors} errors out of {total}",
        "add_files_first": "Add PDF files first.",
        "select_pdf": "Select PDF files",
        "pdf_files": "PDF Files",
        "all_files": "All files",
        "choose_output": "Choose where to save compressed PDF files",
        "lang_label": "Language:",
        "msg_lossless": "Lossless optimization...",
        "msg_recompress": "Recompressing images at {dpi} DPI, quality {quality}...",
    },
    "ro": {
        "app_title": "Compresor PDF",
        "subtitle": "Trageți și plasați fișiere PDF mai jos, apoi apăsați Comprimare. Fișierele originale nu sunt modificate niciodată.",
        "footer_brand": "2026   ·   Versiunea 1.0",
        "placeholder": "⊕   Plasați fișierele PDF aici  ·  sau faceți click pentru a răsfoi",
        "btn_clear_all": "Șterge tot",
        "btn_remove_selected": "Elimină selecția",
        "btn_output_dir": "Folder destinație…",
        "btn_compress": "Comprimare",
        "btn_compressing": "Se comprimă…",
        "col_name": "Nume",
        "col_path": "Cale",
        "col_current": "Dimensiune actuală",
        "col_result": "Rezultat",
        "col_status": "Stare",
        "no_files": "Niciun fișier încărcat.",
        "n_files_1": "1 fișier încărcat.",
        "n_files_n": "{n} fișiere încărcate.",
        "save_next_to": "Salvare lângă fiecare fișier original",
        "save_in": "Salvare în: {path}   (clic pentru resetare)",
        "ready": "Pregătit",
        "time_elapsed": "Timp scurs: {t}",
        "preparing": "Se pregătește…  (0/{total})",
        "compressing_file": "Se comprimă {name}  ({idx}/{total})…",
        "step_progress": "{name}  ({idx}/{total})  —  {msg}",
        "waiting": "În așteptare",
        "compressing": "Se comprimă…",
        "done_result": "Gata  —  {msg}",
        "error_result": "Eroare: {msg}",
        "total_time": "Timp total: {t}",
        "done_1": "Gata  —  1 fișier comprimat",
        "done_n": "Gata  —  {total} fișiere comprimate",
        "done_errors": "Gata  —  {ok} reușite, {errors} cu erori din {total}",
        "add_files_first": "Adăugați mai întâi fișiere PDF.",
        "select_pdf": "Selectați fișiere PDF",
        "pdf_files": "Fișiere PDF",
        "all_files": "Toate fișierele",
        "choose_output": "Alegeți unde să salvați fișierele PDF comprimate",
        "lang_label": "Limbă:",
        "msg_lossless": "Optimizare fără pierderi...",
        "msg_recompress": "Recomprimare imagini la {dpi} DPI, calitate {quality}...",
    },
}

COL_WIDTHS = {
    "name": 220,
    "path": 360,
    "current": 130,
    "result": 110,
    "status": 240,
}

_COMPRESSOR_LOSSLESS_MSG = "Lossless optimization..."
_COMPRESSOR_RECOMPRESS_PREFIX = "Recompressing images at "


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
        self.rows = {}  # item_id -> {"path", "size", "status_key", "result_msg", "error_msg"}
        self.compressing = False
        self.output_dir = None  # None -> save next to each original
        self.start_time = None
        self.lang = "en"

        root.title("PDF Compressor")
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

    def _t(self, key, **kwargs):
        s = STRINGS[self.lang].get(key, STRINGS["en"].get(key, key))
        return s.format(**kwargs) if kwargs else s

    def _translate_compressor_msg(self, msg):
        if self.lang == "en":
            return msg
        if msg == _COMPRESSOR_LOSSLESS_MSG:
            return self._t("msg_lossless")
        if msg.startswith(_COMPRESSOR_RECOMPRESS_PREFIX):
            rest = msg[len(_COMPRESSOR_RECOMPRESS_PREFIX):]
            dpi_part, qual_part = rest.split(", quality ")
            dpi = dpi_part.replace(" DPI", "")
            quality = qual_part.rstrip(".")
            return self._t("msg_recompress").format(dpi=dpi, quality=quality)
        return msg

    # ----- styling --------------------------------------------------------
    def _apply_styles(self):
        style = ttk.Style()
        style.configure("Treeview", rowheight=34, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10),
                        padding=(8, 6))
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
        self.footer_brand_label = ttk.Label(
            footer, text=self._t("footer_brand"), style="AppFooter.TLabel")
        self.footer_brand_label.pack(side="right")

    def _build_header(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill="x", pady=(0, 16))

        # Language selector -- right side of the header bar
        lang_frame = ttk.Frame(header)
        lang_frame.pack(side="right", anchor="n", pady=(4, 0))
        self.lang_label_widget = ttk.Label(
            lang_frame, text=self._t("lang_label"), style="Subtitle.TLabel")
        self.lang_label_widget.pack(side="left", padx=(0, 6))
        self.lang_var = tk.StringVar(value="English")
        self.lang_combo = ttk.Combobox(
            lang_frame, textvariable=self.lang_var,
            values=["English", "Română"], width=9, state="readonly",
        )
        self.lang_combo.pack(side="left")
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)

        # Title and subtitle -- left side
        left = ttk.Frame(header)
        left.pack(side="left", fill="x", expand=True)
        self.title_label = ttk.Label(left, text=self._t("app_title"),
                                     style="Title.TLabel")
        self.title_label.pack(anchor="w")
        self.subtitle_label = ttk.Label(left, text=self._t("subtitle"),
                                        style="Subtitle.TLabel")
        self.subtitle_label.pack(anchor="w", pady=(2, 0))

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
            self.tree.heading(col, text=self._t(f"col_{col}"))
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
            text=self._t("placeholder"),
            font=("Segoe UI", 13), foreground=MUTED, anchor="center",
            cursor="hand2",
        )
        self.placeholder.bind("<Button-1>", self._browse_files)
        self._show_placeholder()

    def _build_controls(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(16, 0))

        self.btn_clear_all = ttk.Button(
            bar, text=self._t("btn_clear_all"), command=self._clear_all)
        self.btn_clear_all.pack(side="left")
        self.btn_remove_selected = ttk.Button(
            bar, text=self._t("btn_remove_selected"), command=self._remove_selected)
        self.btn_remove_selected.pack(side="left", padx=(8, 0))
        self.btn_output_dir = ttk.Button(
            bar, text=self._t("btn_output_dir"), command=self._choose_output_dir)
        self.btn_output_dir.pack(side="left", padx=(8, 0))

        self.output_label = ttk.Label(bar, style="Footer.TLabel")
        self.output_label.pack(side="left", padx=(12, 0))
        self.output_label.bind("<Button-1>", lambda e: self._reset_output_dir())
        self._update_output_label()

        self.footer = ttk.Label(bar, text=self._t("no_files"),
                                style="Footer.TLabel")
        self.footer.pack(side="left", padx=16)

        self.compress_btn = ttk.Button(
            bar, text=self._t("btn_compress"), style="Big.Accent.TButton",
            command=self._start_compression,
        )
        self.compress_btn.pack(side="right")

    def _build_progress(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(14, 0))
        top = ttk.Frame(bar)
        top.pack(fill="x", pady=(0, 5))
        self.progress_label = ttk.Label(top, text=self._t("ready"),
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

    # ----- language -------------------------------------------------------
    def _on_lang_change(self, event=None):
        self.lang = "ro" if self.lang_var.get() == "Română" else "en"
        self._apply_language()

    def _apply_language(self):
        self.root.title(self._t("app_title"))
        self.title_label.config(text=self._t("app_title"))
        self.subtitle_label.config(text=self._t("subtitle"))
        self.footer_brand_label.config(text=self._t("footer_brand"))
        self.lang_label_widget.config(text=self._t("lang_label"))
        self.placeholder.config(text=self._t("placeholder"))
        self.btn_clear_all.config(text=self._t("btn_clear_all"))
        self.btn_remove_selected.config(text=self._t("btn_remove_selected"))
        self.btn_output_dir.config(text=self._t("btn_output_dir"))
        self._update_output_label()
        self._update_footer()
        if self.compressing:
            self.compress_btn.config(text=self._t("btn_compressing"))
        else:
            self.compress_btn.config(text=self._t("btn_compress"))
        for col in COLUMNS:
            self.tree.heading(col, text=self._t(f"col_{col}"))
        self._retranslate_rows()

    def _retranslate_rows(self):
        static_keys = {"ready", "waiting", "compressing"}
        for item, data in self.rows.items():
            sk = data.get("status_key", "ready")
            if sk in static_keys:
                self._set_cell(item, "status", self._t(sk))
            elif sk == "done":
                self._set_cell(item, "status",
                               self._t("done_result", msg=data.get("result_msg", "")))
            elif sk == "error":
                self._set_cell(item, "status",
                               self._t("error_result", msg=data.get("error_msg", "")))

    # ----- progress bar ---------------------------------------------------
    def _progress_begin_file(self, name, idx, total):
        self.progress["value"] = idx - 1
        self.progress_label.config(
            text=self._t("compressing_file", name=name, idx=idx, total=total))

    def _progress_step(self, name, idx, total, step, msg):
        self.progress["value"] = (idx - 1) + min(step / STEPS_PER_FILE, 1.0)
        self.progress_label.config(
            text=self._t("step_progress", name=name, idx=idx, total=total, msg=msg))

    def _progress_finish_file(self, idx):
        self.progress["value"] = idx

    def _tick(self):
        """Update elapsed time once a second while compressing."""
        if not self.compressing or self.start_time is None:
            return
        elapsed = time.monotonic() - self.start_time
        self.time_label.config(text=self._t("time_elapsed", t=fmt_duration(elapsed)))
        self.root.after(1000, self._tick)

    # ----- empty-state placeholder ----------------------------------------
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
            title=self._t("select_pdf"),
            filetypes=[(self._t("pdf_files"), "*.pdf"),
                       (self._t("all_files"), "*.*")],
        )
        if paths:
            self._add_paths(paths)

    # ----- output folder --------------------------------------------------
    def _choose_output_dir(self):
        if self.compressing:
            return
        folder = filedialog.askdirectory(title=self._t("choose_output"))
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
                text=self._t("save_in", path=disp), cursor="hand2")
        else:
            self.output_label.config(
                text=self._t("save_next_to"), cursor="")

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
                    self._t("ready")),
        )
        self.rows[item] = {
            "path": path, "size": size,
            "status_key": "ready", "result_msg": "", "error_msg": "",
        }
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
            base = self._t("no_files")
        elif n == 1:
            base = self._t("n_files_1")
        else:
            base = self._t("n_files_n", n=n)
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

    def _set_row_meta(self, item, **kwargs):
        if item in self.rows:
            self.rows[item].update(kwargs)

    def _ui(self, fn, *args):
        self.root.after(0, lambda: fn(*args))

    def _start_compression(self):
        if self.compressing:
            return
        if not self.rows:
            messagebox.showinfo(self._t("app_title"), self._t("add_files_first"))
            return
        self.compressing = True
        self.start_time = time.monotonic()
        self.compress_btn.config(state="disabled", text=self._t("btn_compressing"))
        total = len(self.rows)
        self.progress.config(maximum=total, value=0)
        self.progress_label.config(text=self._t("preparing", total=total))
        self.time_label.config(text=self._t("time_elapsed", t="0:00"))
        self._tick()
        for item in self.rows:
            self._set_cell(item, "result", "")
            self._set_cell(item, "status", self._t("waiting"))
            self.rows[item]["status_key"] = "waiting"
            self._set_status_tag(item, None)
        snapshot = [(item, dict(data)) for item, data in self.rows.items()]
        threading.Thread(target=self._worker, args=(snapshot, self.output_dir),
                         daemon=True).start()

    def _worker(self, snapshot, out_dir):
        total = len(snapshot)
        errors = 0
        for idx, (item, data) in enumerate(snapshot, start=1):
            name = os.path.basename(data["path"])
            self._ui(self._set_cell, item, "status", self._t("compressing"))
            self._ui(self._set_row_meta, item, status_key="compressing")
            self._ui(self._progress_begin_file, name, idx, total)
            step_count = [0]

            def progress(msg, _item=item, _name=name, _idx=idx):
                step_count[0] += 1
                display_msg = self._translate_compressor_msg(msg)
                self._ui(self._set_cell, _item, "status", display_msg)
                self._ui(self._progress_step, _name, _idx, total,
                         step_count[0], display_msg)

            try:
                out_path = unique_output_path(data["path"], out_dir)
                result = compress_pdf(data["path"], out_path,
                                      progress_cb=progress)
                self._ui(self._apply_result, item, result)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                self._ui(self._apply_error, item, str(exc))
            self._ui(self._progress_finish_file, idx)
        self._ui(self._finish_compression, total, errors)

    def _apply_result(self, item, result):
        if item not in self.rows:
            return
        self._set_cell(item, "result", fmt_kb(result.final_bytes))
        self._set_cell(item, "status", self._t("done_result", msg=result.message))
        self.rows[item]["status_key"] = "done"
        self.rows[item]["result_msg"] = result.message
        self._set_status_tag(item, "done")

    def _apply_error(self, item, message):
        if item not in self.rows:
            return
        self._set_cell(item, "result", "—")
        self._set_cell(item, "status", self._t("error_result", msg=message))
        self.rows[item]["status_key"] = "error"
        self.rows[item]["error_msg"] = message
        self._set_status_tag(item, "error")

    def _finish_compression(self, total=0, errors=0):
        self.compressing = False
        self.compress_btn.config(state="normal", text=self._t("btn_compress"))
        self.progress["value"] = self.progress["maximum"]
        if self.start_time is not None:
            elapsed = time.monotonic() - self.start_time
            self.time_label.config(text=self._t("total_time", t=fmt_duration(elapsed)))
        if errors:
            ok = total - errors
            self.progress_label.config(
                text=self._t("done_errors", ok=ok, errors=errors, total=total))
        elif total == 1:
            self.progress_label.config(text=self._t("done_1"))
        else:
            self.progress_label.config(text=self._t("done_n", total=total))


def main():
    root = TkinterDnD.Tk()
    PdfCompressorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
