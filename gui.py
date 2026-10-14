# ── gui.py ────────────────────────────────────────────────────────────────────
# Tkinter GUI for P3CC — the whole non-technical-facing UI surface.
# main.py stays orchestration-only; this module wires its run_pipeline()
# to a window instead of the console. No business logic lives here either.
# ──────────────────────────────────────────────────────────────────────────────

import copy
import logging
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

import field_map_store
from exceptions import P3CCError
from main import run_pipeline
from settings import get_resource_path, load_settings, save_settings
from utils import select_file, load_excel

log = logging.getLogger(__name__)

# (display label, internal processor key) — shown in the Manage Fields dialog
PROCESSOR_CHOICES = [
    ('Plain text', None),
    ('Strip blank / N-A values', 'col_check'),
    ('Arabic character normalize', 'chr_replace'),
    ('Append .JPG extension', 'jpg'),
]
PROCESSOR_LABELS = {key: label for label, key in PROCESSOR_CHOICES}
PROCESSOR_KEYS = {label: key for label, key in PROCESSOR_CHOICES}

COUNTER_SENTINEL = '__line_count__'


def _format_column(col_def) -> str:
    if col_def is None:
        return '(empty)'
    if col_def == COUNTER_SENTINEL:
        return '(card counter)'
    if isinstance(col_def, list):
        return ', '.join(col_def)
    return str(col_def)


class SettingsDialog(tk.Toplevel):
    """Lets the user browse-pick the two remembered default folders."""

    def __init__(self, parent: tk.Tk, settings: dict, on_save):
        super().__init__(parent)
        self.title('Settings')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._settings = dict(settings)
        self._on_save = on_save

        self._source_var = tk.StringVar(value=self._settings['last_source_folder'])
        self._excel_var = tk.StringVar(value=self._settings['last_excel_folder'])

        self._row('Default P3 source folder:', self._source_var, self._browse_source, 0)
        self._row('Default Excel folder:', self._excel_var, self._browse_excel, 1)

        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, columnspan=3, pady=(10, 10))
        ttk.Button(btns, text='Save', command=self._save).pack(side='left', padx=5)
        ttk.Button(btns, text='Cancel', command=self.destroy).pack(side='left', padx=5)

    def _row(self, label, var, browse_cmd, row):
        ttk.Label(self, text=label).grid(row=row, column=0, sticky='w', padx=10, pady=8)
        ttk.Entry(self, textvariable=var, width=45).grid(row=row, column=1, padx=5, pady=8)
        ttk.Button(self, text='Browse…', command=browse_cmd).grid(row=row, column=2, padx=(0, 10), pady=8)

    def _browse_source(self):
        folder = filedialog.askdirectory(initialdir=self._source_var.get() or '.')
        if folder:
            self._source_var.set(folder)

    def _browse_excel(self):
        folder = filedialog.askdirectory(initialdir=self._excel_var.get() or '.')
        if folder:
            self._excel_var.set(folder)

    def _save(self):
        self._settings['last_source_folder'] = self._source_var.get() or '.'
        self._settings['last_excel_folder'] = self._excel_var.get() or '.'
        save_settings(self._settings)
        self._on_save(self._settings)
        self.destroy()


class FieldEditDialog(tk.Toplevel):
    """Add or edit a single tag → Excel-column mapping."""

    def __init__(self, parent: tk.Tk, excel_columns: list[str], field: dict | None, on_save):
        super().__init__(parent)
        self.title('Field' if field is None else 'Edit Field')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._on_save = on_save
        field = field or {'tag': '', 'column': '', 'processor': None}

        is_counter = field['column'] == COUNTER_SENTINEL
        is_empty = field['column'] is None
        column_text = '' if (is_counter or is_empty) else _format_column(field['column'])

        self._tag_var = tk.StringVar(value=field['tag'])
        self._source_mode = tk.StringVar(value='counter' if is_counter else ('empty' if is_empty else 'excel'))
        self._column_var = tk.StringVar(value=column_text)
        self._processor_var = tk.StringVar(
            value=next((label for label, key in PROCESSOR_CHOICES if key == field['processor']), 'Plain text')
        )

        row = 0
        ttk.Label(self, text='Tag (e.g. <address>):').grid(row=row, column=0, sticky='w', padx=10, pady=8)
        ttk.Entry(self, textvariable=self._tag_var, width=30).grid(row=row, column=1, columnspan=2, sticky='w', padx=5, pady=8)

        row += 1
        ttk.Label(self, text='Value source:').grid(row=row, column=0, sticky='nw', padx=10, pady=8)
        mode_frame = ttk.Frame(self)
        mode_frame.grid(row=row, column=1, columnspan=2, sticky='w', padx=5, pady=8)
        ttk.Radiobutton(mode_frame, text='From Excel column(s)', variable=self._source_mode,
                         value='excel', command=self._sync_column_state).pack(anchor='w')
        ttk.Radiobutton(mode_frame, text='Card counter (running card number)', variable=self._source_mode,
                         value='counter', command=self._sync_column_state).pack(anchor='w')
        ttk.Radiobutton(mode_frame, text='Empty (no value)', variable=self._source_mode,
                         value='empty', command=self._sync_column_state).pack(anchor='w')

        row += 1
        ttk.Label(self, text='Excel column:').grid(row=row, column=0, sticky='w', padx=10, pady=8)
        self._column_box = ttk.Combobox(self, textvariable=self._column_var, values=excel_columns, width=32)
        self._column_box.grid(row=row, column=1, columnspan=2, sticky='w', padx=5, pady=8)
        ttk.Label(self, text='(comma-separate for fallbacks, first found wins)',
                  foreground='#666').grid(row=row + 1, column=1, columnspan=2, sticky='w', padx=5)

        row += 2
        ttk.Label(self, text='Transform:').grid(row=row, column=0, sticky='w', padx=10, pady=8)
        ttk.Combobox(self, textvariable=self._processor_var, values=[label for label, _ in PROCESSOR_CHOICES],
                     state='readonly', width=30).grid(row=row, column=1, columnspan=2, sticky='w', padx=5, pady=8)

        row += 1
        btns = ttk.Frame(self)
        btns.grid(row=row, column=0, columnspan=3, pady=(12, 10))
        ttk.Button(btns, text='Save', command=self._save).pack(side='left', padx=5)
        ttk.Button(btns, text='Cancel', command=self.destroy).pack(side='left', padx=5)

        self._sync_column_state()

    def _sync_column_state(self):
        self._column_box.config(state='normal' if self._source_mode.get() == 'excel' else 'disabled')

    def _save(self):
        tag = self._tag_var.get().strip()
        if not tag:
            messagebox.showerror('Field', 'Tag cannot be empty.')
            return

        mode = self._source_mode.get()
        if mode == 'counter':
            column = COUNTER_SENTINEL
        elif mode == 'empty':
            column = None
        else:
            raw = self._column_var.get().strip()
            if not raw:
                messagebox.showerror('Field', 'Choose or type an Excel column, or pick a different value source.')
                return
            parts = [p.strip() for p in raw.split(',') if p.strip()]
            column = parts[0] if len(parts) == 1 else parts

        processor = PROCESSOR_KEYS.get(self._processor_var.get())
        self._on_save({'tag': tag, 'column': column, 'processor': processor})
        self.destroy()


class FieldMapDialog(tk.Toplevel):
    """
    Lets a non-technical user add/edit/delete/reorder the Excel-column → p3-tag
    mappings for each profile, without touching config.py. Changes save to
    field_map.json and take effect on the next Run (no restart needed).
    """

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.title('Manage Fields')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._field_map = copy.deepcopy(field_map_store.load_field_map())
        self._excel_columns: list[str] = []
        profiles = field_map_store.profile_names()
        self._profile_var = tk.StringVar(value=profiles[0] if profiles else '')

        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=(10, 4))
        ttk.Label(top, text='Profile:').pack(side='left')
        profile_box = ttk.Combobox(top, textvariable=self._profile_var, values=profiles,
                                    state='readonly', width=20)
        profile_box.pack(side='left', padx=(6, 20))
        profile_box.bind('<<ComboboxSelected>>', lambda e: self._refresh_tree())
        ttk.Button(top, text='Load Sample Excel…', command=self._load_sample_excel).pack(side='left')

        columns = ('tag', 'source', 'transform')
        self.tree = ttk.Treeview(self, columns=columns, show='headings', height=10)
        self.tree.heading('tag', text='Tag')
        self.tree.heading('source', text='Value Source')
        self.tree.heading('transform', text='Transform')
        self.tree.column('tag', width=160)
        self.tree.column('source', width=260)
        self.tree.column('transform', width=180)
        self.tree.pack(fill='both', expand=True, padx=10, pady=6)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill='x', padx=10, pady=(0, 6))
        ttk.Button(btn_row, text='Add…', command=self._add_field).pack(side='left', padx=2)
        ttk.Button(btn_row, text='Edit…', command=self._edit_field).pack(side='left', padx=2)
        ttk.Button(btn_row, text='Delete', command=self._delete_field).pack(side='left', padx=2)
        ttk.Button(btn_row, text='Move Up', command=lambda: self._move_field(-1)).pack(side='left', padx=2)
        ttk.Button(btn_row, text='Move Down', command=lambda: self._move_field(1)).pack(side='left', padx=2)
        ttk.Button(btn_row, text='Reset Profile to Defaults', command=self._reset_profile).pack(side='left', padx=(20, 2))

        bottom = ttk.Frame(self)
        bottom.pack(fill='x', padx=10, pady=(0, 10))
        ttk.Button(bottom, text='Save & Close', command=self._save_and_close).pack(side='left', padx=2)
        ttk.Button(bottom, text='Cancel', command=self.destroy).pack(side='left', padx=2)

        self._refresh_tree()

    # ── Helpers ──────────────────────────────────────────────────────────

    def _current_fields(self) -> list[dict]:
        """Query: the active profile's fields, without creating a profile entry."""
        return self._field_map.get(self._profile_var.get(), [])

    def _current_fields_for_edit(self) -> list[dict]:
        """Command: the active profile's fields, creating an empty list for it
        if this is the first field ever added to that profile."""
        return self._field_map.setdefault(self._profile_var.get(), [])

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, field in enumerate(self._current_fields()):
            self.tree.insert('', 'end', iid=str(i), values=(
                field['tag'],
                _format_column(field['column']),
                PROCESSOR_LABELS.get(field.get('processor'), 'Plain text'),
            ))

    def _selected_index(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _load_sample_excel(self):
        path = filedialog.askopenfilename(title='Select a sample Excel file')
        if not path:
            return
        try:
            self._excel_columns = load_excel(path).columns.tolist()
        except Exception as e:
            messagebox.showerror('Manage Fields', f'Could not read that Excel file:\n{e}')
            return
        messagebox.showinfo('Manage Fields', f'Loaded {len(self._excel_columns)} column names.')

    # ── Field CRUD ───────────────────────────────────────────────────────

    def _add_field(self):
        FieldEditDialog(self, self._excel_columns, None, self._on_field_added)

    def _on_field_added(self, field: dict):
        self._current_fields_for_edit().append(field)
        self._refresh_tree()

    def _edit_field(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showerror('Manage Fields', 'Select a field to edit first.')
            return
        FieldEditDialog(self, self._excel_columns, self._current_fields()[idx],
                         lambda field: self._on_field_edited(idx, field))

    def _on_field_edited(self, idx: int, field: dict):
        self._current_fields_for_edit()[idx] = field
        self._refresh_tree()

    def _delete_field(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showerror('Manage Fields', 'Select a field to delete first.')
            return
        del self._current_fields_for_edit()[idx]
        self._refresh_tree()

    def _move_field(self, direction: int):
        idx = self._selected_index()
        if idx is None:
            return
        fields = self._current_fields_for_edit()
        new_idx = idx + direction
        if 0 <= new_idx < len(fields):
            fields[idx], fields[new_idx] = fields[new_idx], fields[idx]
            self._refresh_tree()
            self.tree.selection_set(str(new_idx))

    def _reset_profile(self):
        profile = self._profile_var.get()
        if not messagebox.askyesno('Manage Fields', f'Reset "{profile}" fields to the built-in defaults?'):
            return
        defaults = field_map_store.default_field_map()
        self._field_map[profile] = copy.deepcopy(defaults.get(profile, []))
        self._refresh_tree()

    def _save_and_close(self):
        field_map_store.save_field_map(self._field_map)
        self.destroy()


class HelpDialog(tk.Toplevel):
    """Shows the project's README content to end users who only ever see the
    packaged .exe and have no other way to read it."""

    _HEADING_FONT = ('Segoe UI', 12, 'bold')

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.title('Help')
        self.geometry('700x600')
        self.transient(parent)

        notebook = ttk.Notebook(self)
        notebook.pack(fill='both', expand=True, padx=8, pady=8)
        notebook.add(self._build_tab(notebook, 'README.md'), text='English')
        notebook.add(self._build_tab(notebook, 'README-ar.md'), text='العربية')

    def _build_tab(self, parent: ttk.Notebook, filename: str) -> ttk.Frame:
        frame = ttk.Frame(parent)
        text = scrolledtext.ScrolledText(frame, wrap='word', font=('Segoe UI', 10))
        text.pack(fill='both', expand=True)
        text.tag_configure('heading', font=self._HEADING_FONT)

        try:
            content = get_resource_path(filename).read_text(encoding='utf-8')
        except OSError as e:
            content = None
            text.insert('end', f'Could not load {filename}: {e}')

        if content is not None:
            self._insert_readme(text, content)

        text.config(state='disabled')
        return frame

    def _insert_readme(self, text: tk.Text, content: str) -> None:
        """Render README markdown as plain readable text: bold '#' headings,
        drop code-fence markers but keep their content. No full markdown
        parsing — this is a help viewer, not a renderer."""
        in_code_block = False
        for line in content.splitlines():
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                continue
            if line.startswith('#') and not in_code_block:
                text.insert('end', line.lstrip('#').strip() + '\n', 'heading')
            else:
                text.insert('end', line + '\n')


class P3CCApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('P3CC — Collect-Comparative')
        self.resizable(False, False)

        self.settings = load_settings()
        self.source_folder: str | None = None
        self.excel_path: str | None = None

        self._build_widgets()

    # ── Layout ───────────────────────────────────────────────────────────

    def _build_widgets(self):
        pad = {'padx': 10, 'pady': 6}

        frame = ttk.Frame(self)
        frame.pack(fill='both', expand=True, padx=10, pady=10)

        # Source folder row
        ttk.Label(frame, text='P3 source folder:').grid(row=0, column=0, sticky='w', **pad)
        self.source_label = ttk.Label(frame, text='(not selected)', width=45, anchor='w')
        self.source_label.grid(row=0, column=1, sticky='w', **pad)
        ttk.Button(frame, text='Choose Folder…', command=self._choose_source_folder).grid(row=0, column=2, **pad)

        # Excel file row
        ttk.Label(frame, text='Excel data file:').grid(row=1, column=0, sticky='w', **pad)
        self.excel_label = ttk.Label(frame, text='(not selected)', width=45, anchor='w')
        self.excel_label.grid(row=1, column=1, sticky='w', **pad)
        ttk.Button(frame, text='Choose File…', command=self._choose_excel_file).grid(row=1, column=2, **pad)

        # Run / Settings buttons
        btn_row = ttk.Frame(frame)
        btn_row.grid(row=2, column=0, columnspan=3, pady=(10, 4))
        self.run_button = ttk.Button(btn_row, text='Run', command=self._on_run)
        self.run_button.pack(side='left', padx=5)
        ttk.Button(btn_row, text='Settings', command=self._open_settings).pack(side='left', padx=5)
        ttk.Button(btn_row, text='Manage Fields', command=self._open_field_map).pack(side='left', padx=5)
        ttk.Button(btn_row, text='Help', command=self._open_help).pack(side='left', padx=5)

        # Progress bar
        self.progress = ttk.Progressbar(frame, orient='horizontal', length=400, mode='determinate')
        self.progress.grid(row=3, column=0, columnspan=3, pady=(6, 6))

        # Results panel
        self.results_var = tk.StringVar(value='')
        results_label = ttk.Label(frame, textvariable=self.results_var, justify='left', anchor='w')
        results_label.grid(row=4, column=0, columnspan=3, sticky='w', **pad)

        self.open_folder_button = ttk.Button(
            frame, text='Open Output Folder', command=self._open_output_folder, state='disabled'
        )
        self.open_folder_button.grid(row=5, column=0, columnspan=3, pady=(0, 6))

        self._last_output_path: Path | None = None

    # ── Actions ──────────────────────────────────────────────────────────

    def _choose_source_folder(self):
        folder = filedialog.askdirectory(
            title='Select the P3 source folder',
            initialdir=self.settings.get('last_source_folder') or '.',
        )
        if folder:
            self.source_folder = folder
            self.source_label.config(text=folder)

    def _choose_excel_file(self):
        try:
            path = select_file(
                title='Select the Excel data file',
                folder=self.settings.get('last_excel_folder') or '.',
            )
        except FileNotFoundError:
            path = select_file(title='Select the Excel data file')
        if path:
            self.excel_path = path
            self.excel_label.config(text=path)

    def _open_settings(self):
        SettingsDialog(self, self.settings, on_save=self._settings_saved)

    def _settings_saved(self, new_settings: dict):
        self.settings = new_settings

    def _open_field_map(self):
        FieldMapDialog(self)

    def _open_help(self):
        HelpDialog(self)

    def _open_output_folder(self):
        if self._last_output_path is not None:
            os.startfile(self._last_output_path.parent)

    def _on_run(self):
        if not self.source_folder:
            messagebox.showerror('P3CC', 'Please choose the P3 source folder first.')
            return
        if not self.excel_path:
            messagebox.showerror('P3CC', 'Please choose the Excel data file first.')
            return

        self.run_button.config(state='disabled')
        self.results_var.set('Processing…')
        self.open_folder_button.config(state='disabled')
        self.progress.config(value=0, maximum=1)

        thread = threading.Thread(target=self._run_pipeline_worker, daemon=True)
        thread.start()

    def _run_pipeline_worker(self):
        try:
            result = run_pipeline(
                Path(self.source_folder),
                self.excel_path,
                progress_callback=self._progress_from_worker,
            )
        except P3CCError as e:
            self.after(0, self._show_error, str(e))
            return
        except Exception:
            log.exception('Unexpected error occurred during card data processing.')
            self.after(0, self._show_error, 'An unexpected error occurred. See p3cc.log for details.')
            return

        self.after(0, self._show_result, result)

    def _progress_from_worker(self, current: int, total: int):
        self.after(0, lambda: self.progress.config(value=current, maximum=max(total, 1)))

    def _show_error(self, message: str):
        self.run_button.config(state='normal')
        self.results_var.set('')
        messagebox.showerror('P3CC — Error', message)

    def _show_result(self, result: dict):
        self.run_button.config(state='normal')
        self._last_output_path = Path(result['output_path'])
        self.results_var.set(
            f"Files processed : {result['file_count']}\n"
            f"Cards read      : {result['total_card_count']}\n"
            f"Cards written   : {result['total_card_count'] - result['skip_count']}\n"
            f"Cards skipped   : {result['skip_count']}\n"
            f"Layout warnings : {result['warning_count']} (details in p3cc.log)\n"
            f"Lines discarded : {result['discard_count']} (details in p3cc.log)\n"
            f"Elapsed time    : {result['elapsed']:.2f} seconds\n"
            f"Output file     : {result['output_path']}"
        )
        self.open_folder_button.config(state='normal')

        self.settings['last_source_folder'] = self.source_folder
        self.settings['last_excel_folder'] = str(Path(self.excel_path).parent)
        save_settings(self.settings)

        messagebox.showinfo('P3CC', 'Processing complete.')


def launch_app():
    app = P3CCApp()
    app.mainloop()


if __name__ == '__main__':
    launch_app()
