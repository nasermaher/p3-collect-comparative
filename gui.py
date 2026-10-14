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
from config import LINE_COUNT_SENTINEL
from exceptions import FieldMapError, P3CCError
from main import run_pipeline
from settings import get_resource_path, load_settings, save_settings
from utils import select_file, load_excel, detect_profile, missing_field_columns

log = logging.getLogger(__name__)

# (display label, internal processor key) — shown in the Manage Profiles dialog
PROCESSOR_CHOICES = [
    ('Plain text', None),
    ('Strip blank / N-A values', 'col_check'),
    ('Arabic character normalize', 'chr_replace'),
    ('Append .JPG extension', 'jpg'),
]
PROCESSOR_LABELS = {key: label for label, key in PROCESSOR_CHOICES}
PROCESSOR_KEYS = {label: key for label, key in PROCESSOR_CHOICES}


def _format_column(col_def) -> str:
    if col_def is None:
        return '(empty)'
    if col_def == LINE_COUNT_SENTINEL:
        return '(card counter)'
    if isinstance(col_def, list):
        return ', '.join(col_def)
    return str(col_def)


def _split_columns(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(',') if p.strip()]


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
        self.title('Add Field' if field is None else 'Edit Field')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._on_save = on_save
        field = field or {'tag': '', 'column': '', 'processor': None}

        is_counter = field['column'] == LINE_COUNT_SENTINEL
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
            column = LINE_COUNT_SENTINEL
        elif mode == 'empty':
            column = None
        else:
            raw = self._column_var.get().strip()
            if not raw:
                messagebox.showerror('Field', 'Choose or type an Excel column, or pick a different value source.')
                return
            parts = _split_columns(raw)
            column = parts[0] if len(parts) == 1 else parts

        processor = PROCESSOR_KEYS.get(self._processor_var.get())
        self._on_save({'tag': tag, 'column': column, 'processor': processor})
        self.destroy()


class ProfileEditDialog(tk.Toplevel):
    """Create or edit a profile's name, identifying columns and card-ID column."""

    def __init__(self, parent: tk.Toplevel, excel_columns: list[str], profile: dict | None,
                 taken_names: set[str], on_save):
        super().__init__(parent)
        self.title('New Profile' if profile is None else 'Edit Profile')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._on_save = on_save
        self._taken = {n.lower() for n in taken_names}
        profile = profile or {'name': '', 'signatures': [], 'lookup_col': ''}

        self._name_var = tk.StringVar(value=profile['name'])
        self._sig_var = tk.StringVar(value=', '.join(profile['signatures']))
        self._lookup_var = tk.StringVar(value=profile['lookup_col'])

        ttk.Label(self, text='Profile name (e.g. debit-cards):').grid(row=0, column=0, sticky='w', padx=10, pady=8)
        ttk.Entry(self, textvariable=self._name_var, width=34).grid(row=0, column=1, sticky='w', padx=5, pady=8)

        ttk.Label(self, text='Identifying Excel column(s):').grid(row=1, column=0, sticky='w', padx=10, pady=(8, 0))
        ttk.Combobox(self, textvariable=self._sig_var, values=excel_columns, width=32).grid(
            row=1, column=1, sticky='w', padx=5, pady=(8, 0))
        ttk.Label(self, text='Comma-separated. ALL must be in the Excel sheet for this profile to be\n'
                             'detected. Add a column that only this card type has to tell it apart.',
                  foreground='#666').grid(row=2, column=1, sticky='w', padx=5)

        ttk.Label(self, text='Card-ID column:').grid(row=3, column=0, sticky='w', padx=10, pady=8)
        ttk.Combobox(self, textvariable=self._lookup_var, values=excel_columns, width=32).grid(
            row=3, column=1, sticky='w', padx=5, pady=8)

        btns = ttk.Frame(self)
        btns.grid(row=4, column=0, columnspan=2, pady=(12, 10))
        ttk.Button(btns, text='Save', command=self._save).pack(side='left', padx=5)
        ttk.Button(btns, text='Cancel', command=self.destroy).pack(side='left', padx=5)

    def _save(self):
        name = self._name_var.get().strip()
        signatures = _split_columns(self._sig_var.get())
        lookup_col = self._lookup_var.get().strip()

        if not name:
            messagebox.showerror('Profile', 'The profile name cannot be empty.', parent=self)
            return
        if name.lower() in self._taken:
            messagebox.showerror('Profile', f'A profile named "{name}" already exists.', parent=self)
            return
        if signatures and not lookup_col:
            messagebox.showerror('Profile', 'Choose the card-ID column.', parent=self)
            return
        if not signatures and not messagebox.askyesno(
                'Profile', 'With no identifying columns, this profile will never be detected '
                           'automatically. Save it anyway?', parent=self):
            return

        self._on_save({'name': name, 'signatures': signatures, 'lookup_col': lookup_col})
        self.destroy()


class ProfileManagerDialog(tk.Toplevel):
    """
    Lets a non-technical user manage card profiles without touching code:
    add / edit / delete profiles (name, identifying columns, card-ID column),
    and add / edit / delete / reorder each profile's Excel-column → p3-tag
    fields. Changes save to field_map.json and take effect on the next Run.
    """

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.withdraw()
        profiles = self._load(parent)
        if profiles is None:
            self.destroy()
            return
        self.deiconify()

        self.title('Manage Profiles')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._profiles: list[dict] = copy.deepcopy(profiles)
        self._excel_columns: list[str] = []
        self._profile_var = tk.StringVar()

        # Profile row
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=(10, 2))
        ttk.Label(top, text='Profile:').pack(side='left')
        self._profile_box = ttk.Combobox(top, textvariable=self._profile_var, state='readonly', width=24)
        self._profile_box.pack(side='left', padx=(6, 12))
        self._profile_box.bind('<<ComboboxSelected>>', lambda e: self._refresh())
        ttk.Button(top, text='New…', command=self._new_profile).pack(side='left', padx=2)
        ttk.Button(top, text='Edit…', command=self._edit_profile).pack(side='left', padx=2)
        ttk.Button(top, text='Delete', command=self._delete_profile).pack(side='left', padx=2)

        self._info_var = tk.StringVar()
        ttk.Label(self, textvariable=self._info_var, foreground='#333').pack(fill='x', padx=10, pady=(2, 4))

        # Fields
        columns = ('tag', 'source', 'transform')
        self.tree = ttk.Treeview(self, columns=columns, show='headings', height=10)
        self.tree.heading('tag', text='Tag')
        self.tree.heading('source', text='Value Source')
        self.tree.heading('transform', text='Transform')
        self.tree.column('tag', width=160)
        self.tree.column('source', width=260)
        self.tree.column('transform', width=180)
        self.tree.pack(fill='both', expand=True, padx=10, pady=4)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill='x', padx=10, pady=(0, 6))
        ttk.Button(btn_row, text='Add Field…', command=self._add_field).pack(side='left', padx=2)
        ttk.Button(btn_row, text='Edit Field…', command=self._edit_field).pack(side='left', padx=2)
        ttk.Button(btn_row, text='Delete Field', command=self._delete_field).pack(side='left', padx=2)
        ttk.Button(btn_row, text='Move Up', command=lambda: self._move_field(-1)).pack(side='left', padx=2)
        ttk.Button(btn_row, text='Move Down', command=lambda: self._move_field(1)).pack(side='left', padx=2)

        # Excel test
        excel_row = ttk.Frame(self)
        excel_row.pack(fill='x', padx=10, pady=(4, 6))
        ttk.Button(excel_row, text='Test with Excel File…', command=self._test_excel).pack(side='left', padx=2)
        ttk.Label(excel_row, text='shows which profile an Excel sheet selects, and loads its column names',
                  foreground='#666').pack(side='left', padx=6)

        bottom = ttk.Frame(self)
        bottom.pack(fill='x', padx=10, pady=(4, 10))
        ttk.Button(bottom, text='Import…', command=self._import).pack(side='left', padx=2)
        ttk.Button(bottom, text='Reset All to Defaults', command=self._reset_all).pack(side='left', padx=2)
        ttk.Button(bottom, text='Cancel', command=self.destroy).pack(side='right', padx=2)
        ttk.Button(bottom, text='Save & Close', command=self._save_and_close).pack(side='right', padx=2)

        self._refresh(select=self._profiles[0]['name'])

    # ── Loading ──────────────────────────────────────────────────────────

    def _load(self, parent) -> list[dict] | None:
        """Load field_map.json; on failure, offer a reset (with backup) instead
        of silently overwriting the user's file."""
        try:
            profiles, notice = field_map_store.load_profiles_report()
        except FieldMapError as e:
            if not messagebox.askyesno(
                    'Manage Profiles',
                    f'field_map.json could not be loaded:\n\n{e}\n\n'
                    'Reset it to the built-in defaults? The current file is kept as a backup copy.\n'
                    'Choose "No" to fix the file by hand first.', icon='warning', parent=parent):
                return None
            backup = field_map_store.reset_to_defaults()
            if backup:
                messagebox.showinfo('Manage Profiles', f'Previous file saved as {backup.name}.', parent=parent)
            return field_map_store.load_profiles()
        if notice:
            messagebox.showinfo('Manage Profiles', notice, parent=parent)
        return profiles

    # ── Helpers ──────────────────────────────────────────────────────────

    def _current(self) -> dict | None:
        name = self._profile_var.get()
        return next((p for p in self._profiles if p['name'] == name), None)

    def _refresh(self, select: str | None = None):
        names = [p['name'] for p in self._profiles]
        self._profile_box.config(values=names)
        if select is not None:
            self._profile_var.set(select)
        elif self._profile_var.get() not in names:
            self._profile_var.set(names[0] if names else '')

        profile = self._current()
        self.tree.delete(*self.tree.get_children())
        if profile is None:
            self._info_var.set('')
            return
        if profile['signatures']:
            self._info_var.set(f"Identified by: {', '.join(profile['signatures'])}     |     "
                               f"Card-ID column: {profile['lookup_col']}")
        else:
            self._info_var.set('No identifying columns — never detected automatically. Use Edit… to set them.')
        for i, field in enumerate(profile['fields']):
            self.tree.insert('', 'end', iid=str(i), values=(
                field['tag'],
                _format_column(field['column']),
                PROCESSOR_LABELS.get(field.get('processor'), 'Plain text'),
            ))

    def _selected_index(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    # ── Profile CRUD ─────────────────────────────────────────────────────

    def _new_profile(self):
        taken = {p['name'] for p in self._profiles}
        ProfileEditDialog(self, self._excel_columns, None, taken, self._on_profile_added)

    def _on_profile_added(self, data: dict):
        self._profiles.append({**data, 'fields': []})
        self._refresh(select=data['name'])

    def _edit_profile(self):
        profile = self._current()
        if profile is None:
            return
        taken = {p['name'] for p in self._profiles if p is not profile}
        ProfileEditDialog(self, self._excel_columns, profile, taken,
                          lambda data: self._on_profile_edited(profile, data))

    def _on_profile_edited(self, profile: dict, data: dict):
        profile.update(data)
        self._refresh(select=data['name'])

    def _delete_profile(self):
        profile = self._current()
        if profile is None:
            return
        if len(self._profiles) == 1:
            messagebox.showerror('Manage Profiles', 'At least one profile must remain.', parent=self)
            return
        if not messagebox.askyesno('Manage Profiles',
                                   f'Delete profile "{profile["name"]}" and all its fields?', parent=self):
            return
        self._profiles.remove(profile)
        self._refresh(select=self._profiles[0]['name'])

    # ── Field CRUD ───────────────────────────────────────────────────────

    def _add_field(self):
        if self._current() is not None:
            FieldEditDialog(self, self._excel_columns, None, self._on_field_added)

    def _on_field_added(self, field: dict):
        self._current()['fields'].append(field)
        self._refresh()

    def _edit_field(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showerror('Manage Profiles', 'Select a field to edit first.', parent=self)
            return
        FieldEditDialog(self, self._excel_columns, self._current()['fields'][idx],
                        lambda field: self._on_field_edited(idx, field))

    def _on_field_edited(self, idx: int, field: dict):
        self._current()['fields'][idx] = field
        self._refresh()

    def _delete_field(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showerror('Manage Profiles', 'Select a field to delete first.', parent=self)
            return
        del self._current()['fields'][idx]
        self._refresh()

    def _move_field(self, direction: int):
        idx = self._selected_index()
        if idx is None:
            return
        fields = self._current()['fields']
        new_idx = idx + direction
        if 0 <= new_idx < len(fields):
            fields[idx], fields[new_idx] = fields[new_idx], fields[idx]
            self._refresh()
            self.tree.selection_set(str(new_idx))

    # ── Excel test / import / reset / save ───────────────────────────────

    def _test_excel(self):
        path = filedialog.askopenfilename(title='Select an Excel file to test', parent=self)
        if not path:
            return
        try:
            self._excel_columns = load_excel(path).columns.tolist()
        except Exception as e:
            messagebox.showerror('Manage Profiles', f'Could not read that Excel file:\n{e}', parent=self)
            return

        try:
            profile = detect_profile(self._excel_columns, self._profiles)
        except P3CCError as e:
            messagebox.showwarning('Test with Excel File',
                                   f'Loaded {len(self._excel_columns)} column names, but:\n\n{e}', parent=self)
            return

        self._refresh(select=profile['name'])
        message = (f'This sheet selects profile "{profile["name"]}" '
                   f'(card-ID column "{profile["lookup_col"]}").')
        missing = missing_field_columns(profile, self._excel_columns)
        if missing:
            messagebox.showwarning('Test with Excel File',
                                   f'{message}\n\nBut the sheet has no column for these tags, so every '
                                   f'card would be skipped:\n{", ".join(missing)}', parent=self)
        else:
            messagebox.showinfo('Test with Excel File', f'{message}\n\nAll its field columns were found.',
                                parent=self)

    def _import(self):
        path = filedialog.askopenfilename(title='Import a field_map.json file', parent=self,
                                          filetypes=[('JSON files', '*.json'), ('All files', '*.*')])
        if not path:
            return
        try:
            profiles, notice = field_map_store.read_field_map_file(Path(path))
        except FieldMapError as e:
            messagebox.showerror('Import', str(e), parent=self)
            return
        if not messagebox.askyesno('Import', f'Replace the current profiles with the {len(profiles)} '
                                             'profile(s) from this file?\n(Applied when you Save & Close.)',
                                   parent=self):
            return
        if notice:
            messagebox.showinfo('Import', notice, parent=self)
        self._profiles = profiles
        self._refresh(select=profiles[0]['name'])

    def _reset_all(self):
        if not messagebox.askyesno('Manage Profiles',
                                   'Replace ALL profiles with the built-in defaults?\n'
                                   '(Applied when you Save & Close.)', parent=self):
            return
        self._profiles = field_map_store.default_profiles()
        self._refresh(select=self._profiles[0]['name'])

    def _save_and_close(self):
        try:
            field_map_store.save_profiles(self._profiles)
        except FieldMapError as e:
            messagebox.showerror('Manage Profiles', f'Not saved:\n\n{e}', parent=self)
            return
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
        self.after(200, self._check_field_map)

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
        ttk.Button(btn_row, text='Manage Profiles', command=self._open_profiles).pack(side='left', padx=5)
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

    def _open_profiles(self):
        ProfileManagerDialog(self)

    def _check_field_map(self):
        """At startup, surface a broken or just-migrated field_map.json right
        away, rather than on the first Run."""
        try:
            _, notice = field_map_store.load_profiles_report()
        except FieldMapError as e:
            messagebox.showerror('P3CC — field_map.json',
                                 f'{e}\n\nFix the file, or open Manage Profiles to reset it.')
            return
        if notice:
            messagebox.showinfo('P3CC — field_map.json', notice)

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
            f"Profile         : {result['profile']}\n"
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

        if result['field_map_notice']:
            messagebox.showinfo('P3CC — field_map.json', result['field_map_notice'])
        messagebox.showinfo('P3CC', 'Processing complete.')


def launch_app():
    app = P3CCApp()
    app.mainloop()


if __name__ == '__main__':
    launch_app()
