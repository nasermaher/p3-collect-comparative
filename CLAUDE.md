# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

P3CC (P3 Collect-Comparative) is a Windows desktop utility that merges cardholder data from an Excel spreadsheet into `.p3` card-issuance files. It scans `.p3` source files for card-ID markers, looks up the matching Excel row, and injects tagged fields (e.g. `<arabic>`, `<national>`, `<barcode>`) into the output before the `#END#` marker of each card record.

It ships as a Tkinter GUI (`app.py`/`gui.py`), packaged with PyInstaller into a standalone `P3CC.exe` so end users (non-technical staff, machines without Python installed) never touch a terminal.

## Commands

```bash
pip install -r requirements-dev.txt         # runtime deps + pyinstaller
python app.py                               # run the GUI (source/dev mode)
python main.py                              # minimal console entry point, for debugging the pipeline without Tkinter
pyinstaller P3CC.spec                       # rebuild dist/P3CC/P3CC.exe from the committed spec (preferred — preserves hidden-import fixes)
pyinstaller --windowed --name P3CC app.py   # regenerates P3CC.spec from scratch; only do this deliberately, then re-commit the spec
run.bat                                     # dev-only: activates .venv then runs python main.py
```

There is no test suite, linter, or CI config in this repo — `test.py` is a Python-Arabic-codepoint scratch file, not a real test. When making changes, verify manually by running `python app.py` (or `run_pipeline()` directly) against sample data (see `p3_PILOT HOME DELIVERY 20-05-2026/` for example input files).

## Architecture

Strict separation of concerns — **logic and data are never mixed**:

- **`config.py`** — pure data, no logic, developer-only (never edited by the GUI). `ENCODING` (`cp1256`), binary markers (`CARD_MARKER = b'"%B'`, `END_MARKER = b'#END#'`), card-ID byte offsets, `PROFILE_SIGNATURES`, `NORMALIZATION_TABLE`, and `FIELD_MAP` (now just the built-in seed/reset data — see below).
- **`utils.py`** — pure, side-effect-free helper functions (data transforms, profile detection, text building) plus the one necessary UI call (`select_file`, Tkinter file dialog). Every function is independently testable in isolation from `main.py`'s I/O loop.
- **`main.py`** — orchestration only. `run_pipeline(p3_root, excel_path, progress_callback=None)` is the reusable core: resolves output path → discovers source files → loads Excel → detects profile → streams each `.p3` file byte-by-byte, rewriting it with injected fields → returns a summary dict. `main()` is a thin console wrapper around it for dev debugging. Contains no business logic itself.
- **`exceptions.py`** — `P3CCError` base class with `ProfileDetectionError`, `SourceFilesError`, `MissingColumnError`, `InvalidCardError` subclasses for precise error handling.
- **`settings.py`** — loads/saves `settings.json` (remembered folders) next to the running exe (`get_app_dir()`, frozen-aware). Falls back to defaults on any missing/corrupt file, never raises.
- **`field_map_store.py`** — loads/saves `field_map.json` (the user-editable field mappings — see below) next to the exe, seeded from `config.FIELD_MAP` on first run.
- **`gui.py`** — all Tkinter UI: main window, Settings dialog, Manage Fields dialog (`FieldMapDialog`/`FieldEditDialog`), progress bar, results panel, error dialogs. Runs `run_pipeline()` on a background thread.
- **`app.py`** — the GUI entry point; what PyInstaller packages.

### The profile system (the extension point)

Different customers' Excel exports have different columns. A "profile" (`yalla`, `classic`, `zamalek`) is auto-detected from which columns are present, then drives how fields are mapped into the `.p3` output.

**Which columns exist and which profile they belong to (`PROFILE_SIGNATURES`) is a developer-only change in `config.py`** — a wrong signature breaks auto-detection for every user of that profile:

1. Add an entry to `PROFILE_SIGNATURES`: the list of column names that must all be present to identify this profile, and which column is the `lookup_col` (card-ID key used to index the DataFrame). Dict order matters — first matching profile wins (`detect_profile` in `utils.py`).
2. Add a matching entry to `config.FIELD_MAP` so there's seed data for the new profile the first time a user opens Manage Fields for it.

**Which Excel column feeds which `.p3` tag, for an *existing* profile, is user-editable** — from the GUI's Manage Fields dialog (`gui.FieldMapDialog`), not a code change. This exists because that mapping changes often in practice (a customer adds/drops an Excel column and the corresponding output tag needs to follow). It's stored in `field_map.json` next to the exe:

- Each field is `{"tag": "<output_tag>", "column": col_def, "processor": processor_key}`.
- `col_def`: an Excel column name (str), a list of fallback column names (first found wins), `null` (tag written empty), or the sentinel `"__line_count__"` (injects the running card counter).
- `processor_key`: a string key into `utils.py`'s `_PROCESSOR_REGISTRY` (`'col_check'` strips/NaN-guards, `'chr_replace'` normalizes Arabic characters, `'jpg'` appends `.JPG`), or `null` for plain `str()` conversion.
- `field_map_store.load_field_map()` seeds `field_map.json` from `config.FIELD_MAP` on first run, and falls back to those same built-in defaults if the file goes missing or corrupt. The Manage Fields dialog also has a per-profile "Reset to Defaults" button that does the same.
- `utils.get_resolved_field_map()` loads the current `field_map.json` and resolves processor keys to callables; `main.run_pipeline()` calls it once per batch (not once per card) and passes the result into `utils.build_text()`, so edits made in the GUI take effect on the next Run with no restart needed.

### The `.p3` file processing loop (`main.py`)

Files are read and written as raw bytes (not text) because encoding (`cp1256`) must be controlled precisely and markers are matched as byte sequences:

1. Scan each line for `CARD_MARKER` (`"%B`) — when found, slice bytes `[11:27]` and decode as the card ID.
2. Scan for `END_MARKER` (`#END#`) — when found, strip the line's trailing CRLF, look up the card ID in the Excel DataFrame (indexed on `lookup_col` for O(1) lookup), and call `build_text()` to render the tagged field string for that profile, which gets spliced in right after the `#END#` line (via `seek`/`write`, replacing the stripped line-ending bytes).
3. A `KeyError` (card ID not in Excel, or a required column missing) skips that card with a warning rather than aborting the whole batch.

### Arabic text handling

`config.NORMALIZATION_TABLE` + `utils._replaced` (the `chr_replace` processor) normalize Eastern Arabic-Indic digits to ASCII and map a couple of special codepoints (ف, RLM) to `_`; any codepoint above 65381 is also replaced with `_`. This matters because the target `.p3` format only supports `cp1256`-encodable output.

## Portability & settings

- Packaged via PyInstaller (`--windowed`, one-folder) so end users run `dist/P3CC/P3CC.exe` with no Python installed. Distribute the whole `dist/P3CC/` folder as a unit, not just the `.exe`.
- `settings.py` and `field_map_store.py` both resolve their JSON files next to the running exe via `settings.get_app_dir()` (frozen-aware: `sys.executable`'s folder when packaged, this script's folder in source mode) — never `%APPDATA%`, so the whole app folder stays portable across machines/drives.
- `settings.json` and `field_map.json` (along with `p3cc.log`) are runtime-generated and gitignored — don't hand-edit or commit them. If missing or corrupt, they're silently reseeded from `settings.DEFAULT_SETTINGS` / `config.FIELD_MAP`.
- `main.py`'s logging setup only adds a console `StreamHandler` if `sys.stderr is not None` — a `--windowed` build has no console, and `sys.stderr` is `None` there, so adding one unconditionally would crash on the first log call.
