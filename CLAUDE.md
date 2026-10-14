# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Project history, past decisions, the owner's working agreements and open ideas are in `PROJECT_HISTORY.md`. Read it before starting new work:

@PROJECT_HISTORY.md

## Overview

P3CC (P3 Collect-Comparative) is a Windows desktop utility that merges cardholder data from an Excel spreadsheet into `.p3` card-issuance files. It scans `.p3` source files for card-ID markers, looks up the matching Excel row, and injects tagged fields (e.g. `<arabic>`, `<national>`, `<barcode>`) into the output directly after the `#END#` marker of each card record, as a continuation of the same line.

It ships as a Tkinter GUI (`app.py`/`gui.py`), packaged with PyInstaller into a standalone `P3CC.exe` so end users (non-technical staff, machines without Python installed) never touch a terminal.

## Commands

```bash
pip install -r requirements-dev.txt         # runtime deps + pyinstaller + pytest
python app.py                               # run the GUI (source/dev mode)
python main.py                              # minimal console entry point, for debugging the pipeline without the full gui.py window (still uses Tk's native file-picker dialogs)
pytest                                       # run the unit test suite (tests/)
pyinstaller P3CC.spec                       # rebuild dist/P3CC/P3CC.exe from the committed spec (preferred — preserves hidden-import fixes)
pyinstaller --windowed --name P3CC app.py   # regenerates P3CC.spec from scratch; only do this deliberately, then re-commit the spec
run.bat                                     # dev-only: activates .venv then runs python app.py (quick launch — same as toolkit.bat's "Run" option)
toolkit.bat                                 # menu-driven wrapper: run/test/check/setup/package (see toolkit.bat itself)
```

CI: GitHub Actions (`.github/workflows/python-app.yml`) runs on every push/PR to `main` with Python 3.10. It runs flake8 (syntax errors and undefined names only, so other lint is advisory) and then `pytest`. There is no local linter config. Unit tests live in `tests/` (pytest, covering `utils.py`'s pure functions, `settings.py`, `field_map_store.py` (validation, migration, error handling), and the record pipeline). Run them with `pytest` after `pip install -r requirements-dev.txt`. `tests/test_records.py` includes a synthetic end-to-end `run_pipeline` byte-for-byte check. Real `.p3`/Excel data is confidential and never in the repo. Tests use fake records only, and changes to the pipeline are verified by the owner on real files before committing.

## Architecture

Strict separation of concerns — **logic and data are never mixed**:

- **`config.py`** — pure data, no logic, developer-only (never edited by the GUI). `ENCODING` (`cp1256`), binary markers (`CARD_MARKER = b'"%B'`, `END_MARKER = b'#END#'`), record layout/card-ID byte offsets, `OUTPUT_SUFFIX`, `LINE_COUNT_SENTINEL`, `DEFAULT_PROFILES` (built-in seed/reset profile — see below), the pre-3.2 migration rules (`LEGACY_PROFILE_RENAMES`, `RETIRED_PROFILES`), and `NORMALIZATION_TABLE`.
- **`utils.py`** — pure, side-effect-free helper functions (data transforms, profile detection, text building) plus the one necessary UI call (`select_file`, Tkinter file dialog). Every function is independently testable in isolation from `main.py`'s I/O loop.
- **`main.py`** — orchestration only. `run_pipeline(p3_root, excel_path, progress_callback=None)` is the reusable core: discovers source files (skipping any `*_processed.p3` from a previous run) → names the output after the first source file + `_processed` → loads profiles from `field_map.json` → loads Excel → detects profile (logs any field whose Excel column is missing) → streams each `.p3` file byte-by-byte, rewriting it with injected fields → returns a summary dict. `main()` is a thin console wrapper around it for dev debugging. Contains no business logic itself.
- **`exceptions.py`** — `P3CCError` base class with `ProfileDetectionError`, `SourceFilesError`, `MissingColumnError`, `FieldMapError`, `InvalidCardError` subclasses for precise error handling.
- **`settings.py`** — loads/saves `settings.json` (remembered folders) next to the running exe (`get_app_dir()`, frozen-aware). Falls back to defaults on any missing/corrupt file, never raises.
- **`field_map_store.py`** — loads, validates, migrates, imports, resets and saves `field_map.json` (the user-editable profiles — see below) next to the exe, seeded from `config.DEFAULT_PROFILES` on first run.
- **`gui.py`** — all Tkinter UI: main window, Settings dialog, Manage Profiles dialog (`ProfileManagerDialog` / `ProfileEditDialog` / `FieldEditDialog`), progress bar, results panel, error dialogs. Runs `run_pipeline()` on a background thread. Checks `field_map.json` at startup so a broken or just-migrated file is reported immediately.
- **`app.py`** — the GUI entry point; what PyInstaller packages.

### The profile system (the extension point)

A "profile" is a card type (default: `debit-cards`). It is auto-detected from the Excel sheet's columns and then drives which fields are injected into the `.p3` output. **Profiles are entirely user data**: nothing about them is hardcoded. They live in `field_map.json` next to the exe and are managed from the GUI's Manage Profiles dialog. Adding, renaming or retiring a card type is not a code change.

`field_map.json` format (version 2):

```json
{"version": 2, "profiles": [
  {"name": "debit-cards", "signatures": ["Card No"], "lookup_col": "Card No",
   "fields": [{"tag": "<arabic>", "column": "CardHolder Name", "processor": null}]}
]}
```

- `signatures`: identifying Excel columns. ALL must be present for the profile to match. An empty list means the profile is never auto-detected.
- `lookup_col`: the card-ID column; the DataFrame is indexed on it for O(1) lookup.
- Each field's `column`: an Excel column name, a list of fallback names (first found wins), `null` (tag written empty), or `config.LINE_COUNT_SENTINEL` (`"__line_count__"`, the running card counter). `processor`: a key into `utils._PROCESSOR_REGISTRY` (`'col_check'` strips/NaN-guards, `'chr_replace'` normalizes Arabic characters, `'jpg'` appends `.JPG`), or `null` for plain `str()`.

Detection (`utils.detect_profile(columns, profiles)`): among profiles whose signatures are all present, **the most specific wins** (most signature columns), so list order never matters. An equally specific tie raises `ProfileDetectionError` rather than guessing. A missing `lookup_col` raises `MissingColumnError`.

Loading and safety (`field_map_store`):
- `load_profiles_report()` seeds the file from `config.DEFAULT_PROFILES` if it's missing. If it's unreadable or invalid, it raises `FieldMapError` (with the JSON line/column, if relevant) and **never silently replaces the file**. Before 3.2 the fallback was silent, which made hand-edits look ignored. A UTF-8 BOM is accepted.
- `validate_profiles()` enforces: at least one profile; unique names (case-insensitive); no two profiles with identical signature sets; `lookup_col` set whenever signatures are; well-formed fields with known processors; tags matching `(<[^<>\s]+>)+` and not containing the auto-appended `<cpf>`/`<EOR>` (`tag_problem()`, also used live by the field editor); at least one detectable profile. `save_profiles()` validates first and writes via a temp file plus `os.replace`.
- Pre-3.2 files (`{profile_name: [fields]}`) are migrated on load. The original is backed up as `field_map.pre-3.2-backup-<ts>.json`. `classic` becomes `debit-cards` (fields kept, signatures taken from the default of that name), `yalla`/`zamalek` are dropped, and unknown names are kept with no signatures. These rules live in `config.LEGACY_PROFILE_RENAMES` / `RETIRED_PROFILES`. The migration summary is returned as a notice, which the GUI shows.
- `read_field_map_file()` (used by the dialog's Import…) parses and migrates any file without saving it. `reset_to_defaults()` backs up the current file, even an unreadable one, before rewriting.

`main.run_pipeline()` loads profiles once per batch, so GUI edits apply on the next Run with no restart. It returns the profile name and any migration notice in its summary dict. `utils.resolve_fields(profile)` turns processor keys into callables once per batch for `utils.build_text(fields, row, line_count)`.

### The `.p3` file processing loop (`main.py`)

Files are read and written as raw bytes (not text) because encoding (`cp1256`) must be controlled precisely and markers are matched as byte sequences:

A card record is one *logical* line: `<8-digit serial>"%B<16-digit card ID><encrypted data>#END#`. The encrypted data can contain bare CR, bare LF or CRLF bytes, so physical lines are **not** records and the encrypted bytes must never be altered.

1. `utils.iter_records()` re-joins physical lines into whole records. A record runs from a line that starts with a valid header through the first line ending in `#END#`, so line breaks inside the encrypted data never split it. Only the single line terminator after `#END#` is removed. Lines outside any record (blank lines, header/footer text, junk) are dropped. Each dropped line is logged with its physical line number and byte length, never its content, and the total is returned as `discard_count`.
2. `utils.check_record()` validates the layout (header shape, consecutive serials, `#END#` at end, signs of merged records) and logs warnings to `p3cc.log`. Records with warnings are still processed. Only incomplete records (no `#END#`) are skipped. The count shows up as `warning_count` in the summary and in the GUI.
3. The card ID is `record[11:27]`. It is looked up in the Excel DataFrame (indexed on `lookup_col` for O(1) lookup), and `build_text()`'s tags are written directly after `#END#` as a continuation of the same line. The output file is opened `'ab+'`.
4. A `KeyError` (card ID not in Excel, or a required column missing) skips that card with a warning rather than aborting the whole batch.

`tests/test_records.py` covers this with synthetic records (fake card IDs and payloads with embedded CR/LF), including an end-to-end `run_pipeline` byte-for-byte check.

### Arabic text handling

`config.NORMALIZATION_TABLE` + `utils._replaced` (the `chr_replace` processor) normalize Eastern Arabic-Indic digits to ASCII and map a couple of special codepoints (ڤ Veh, PDF) to `_`; any codepoint above 65381 is also replaced with `_`. This matters because the target `.p3` format only supports `cp1256`-encodable output.

## Portability & settings

- Packaged via PyInstaller (`--windowed`, one-folder) so end users run `dist/P3CC/P3CC.exe` with no Python installed. Distribute the whole `dist/P3CC/` folder as a unit, not just the `.exe`.
- `settings.py` and `field_map_store.py` both resolve their JSON files next to the running exe via `settings.get_app_dir()` (frozen-aware: `sys.executable`'s folder when packaged, this script's folder in source mode) — never `%APPDATA%`, so the whole app folder stays portable across machines/drives.
- `settings.json` and `field_map.json` (along with `p3cc.log`) are runtime-generated and gitignored — don't hand-edit or commit them. A missing file is reseeded from `settings.DEFAULT_SETTINGS` / `config.DEFAULT_PROFILES`. A corrupt `settings.json` silently falls back to defaults, but a corrupt `field_map.json` raises `FieldMapError` and is shown to the user, never overwritten.
- `main.py`'s logging setup only adds a console `StreamHandler` if `sys.stderr is not None` — a `--windowed` build has no console, and `sys.stderr` is `None` there, so adding one unconditionally would crash on the first log call.
