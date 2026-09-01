# PRD: P3CC Portability & Non-Technical Usability

## Context

P3CC currently only runs as a Python script (`python main.py`) launched via `run.bat`, which requires a pre-configured `.venv` with Python already installed on the machine. Its UX is console-only: two raw tkinter file-picker dialogs (one where the user picks *any file inside* the source folder as a workaround for picking the folder itself, one for the Excel file), progress printed via `tqdm` to a console window, and results/errors surfaced only as console text plus a blocking `input('Press Enter to EXIT...')`.

The people who actually run this tool are non-technical staff processing card-issuance batches, often from machines without Python installed, sometimes off a shared/removable drive. The goals of this effort are:

1. **Portability** — the tool must run on any Windows machine with no Python pre-installed.
2. **Usability** — replace the console/raw-dialog flow with a simple GUI a non-technical user can operate without instructions beyond "pick your folder, pick your Excel file, click Run."
3. **Occasional configurability** — let the user change a small set of day-to-day values (remembered folders, etc.) without touching code, while keeping the business-logic constants (`FIELD_MAP`, `PROFILE_SIGNATURES`, `NORMALIZATION_TABLE`, markers) developer-only, since a wrong edit there silently corrupts card output.
4. **Reliable output** — the user should end each run with a clear result: the `.p3` output file produced, obviously located, with an easy way to open its folder, and clear errors instead of stack traces.

Two known bugs (found in a prior audit, not yet fixed) are folded into this effort since the refactor touches the exact code they live in, and both affect reliability for an unattended non-technical user:
- `main.py:166` — `except Exception():` calls `Exception()` instead of catching the class, so it raises a fresh `TypeError` instead of the intended graceful-error path.
- `main.py:109` — `card_id = ''` is set once outside the per-file loop, never reset per file, so a malformed `.p3` file whose first `END_MARKER` precedes any `CARD_MARKER` line silently reuses the previous file's card ID.

**Packaging choice: one-folder PyInstaller build** (not one-file) — faster startup than a self-extracting onefile exe; the whole output folder is distributed/copied as a unit.

## 1. Packaging — standalone executable, no Python required

- Tool: **PyInstaller**, one-folder mode (`--onedir`, the default).
- Add `pyinstaller` to a new `requirements-dev.txt` (kept separate from `requirements.txt`, which documents the app's own runtime deps).
- Entry point for the build is a new `app.py` (see §5), not `main.py`: `pyinstaller --windowed --name P3CC --icon assets/p3cc.ico app.py`.
  - `--windowed`: no console window, appropriate once the GUI (§3) replaces all console I/O.
  - Add a `.ico` under a new `assets/` folder (not currently present).
  - Watch for missing hidden imports around `pandas`/`openpyxl`/`xlrd` (legacy `.xls` support) during the first build — verify with a clean-machine test (§6).
- Distribution: end users get the `dist/P3CC/` folder (containing `P3CC.exe` + supporting files) as a unit — zip it or copy the whole folder, never just the `.exe`. `run.bat` remains for developer use only (`python app.py`/`python main.py` inside `.venv`); it is not part of the end-user distribution.
- Commit the generated `.spec` file after the first successful build (so hidden-import fixes persist for future builds); add `build/` and `dist/` to `.gitignore`.

## 2. Settings mechanism

- Format: **JSON**, file `settings.json` stored **next to `P3CC.exe`** (portable — matches how this tool is actually distributed and run off shared/removable drives; not `%APPDATA%`, which is invisible to this audience and breaks the "copy the folder, it just works" model).
- New module **`settings.py`**: `get_app_dir()` (resolves to the exe's own directory when frozen via PyInstaller, or the script dir in source mode — not the onedir extraction path, since onedir doesn't self-extract to temp the way onefile does, this is simpler than the onefile case), `load_settings()`, `save_settings()`.
- Contents — only what a non-technical user plausibly needs day-to-day:
  - `last_source_folder` — default folder-picker location, updated after each successful run.
  - `last_excel_folder` — same, for the Excel picker.
- Everything else (`ENCODING`, `CARD_MARKER`/`END_MARKER`, `CARD_ID_START`/`END`, `PROFILE_SIGNATURES`, `FIELD_MAP`, `NORMALIZATION_TABLE`) **stays in `config.py`**, untouched by this effort — these define the output data contract and require developer review to change safely.
- First run: if `settings.json` is absent or unreadable, write/fall back to defaults silently (log a warning, never crash on a missing/corrupt settings file).
- Editing UX: a simple Tkinter **Settings dialog** (`Toplevel`) reachable from a "Settings" button on the main window, with browse buttons (`askdirectory`) for the two remembered folders — no raw JSON editing exposed to the user.

## 3. GUI replacement for console UX

New module **`gui.py`** (Tkinter, stdlib only — no new dependency) providing the main window:

- **Folder picker**: replace the current "pick any file inside the folder" workaround (`main.py:52-56`) with a direct `askdirectory(initialdir=settings['last_source_folder'])` call. This removes an unintuitive step for non-technical users.
- **Excel file picker**: keep using the existing `select_file()` helper (`utils.py:167`, wraps `askopenfilename`) — file-grained selection is correct here, no change needed.
- **Run button**: runs the processing pipeline (see §5's `run_pipeline()`) on a background thread so the window stays responsive; marshal progress/results back to the UI thread via `root.after(...)`.
- **Progress bar**: `ttk.Progressbar` (determinate, max = file count), driven by a `progress_callback(current, total)` passed into `run_pipeline()`, replacing the console-only `tqdm` bar (`main.py:111`).
- **Settings button**: opens the dialog from §2.
- **Results panel**: in-window summary (files processed, cards processed/skipped, elapsed time, output file path) replacing the current print/log-only summary (`main.py:176-181`), plus an **"Open output folder"** button (`os.startfile(...)`).
- **Errors**: `messagebox.showerror(...)` for `P3CCError`/`ProfileDetectionError`/`MissingColumnError`/unexpected exceptions, replacing `sys.exit(...)` (`main.py:90`) and the blocking `input('\nPress Enter to EXIT...')` calls (`main.py:163,168,183`) — none of which make sense once there's no console.

## 4. Bug fixes (bundled)

- `main.py:166` — `except Exception():` → `except Exception:`.
- `main.py:109` — move `card_id = ''` inside the per-file loop (alongside `line_count = 0` / `skip_count = 0` at `main.py:115-116`) so it resets for every file instead of leaking from the previous one.
- Both land naturally as part of the `run_pipeline()` extraction in §5, not as a separate patch.

## 5. File/module boundaries

Preserve the existing separation (`config.py` = pure data, `utils.py` = pure helpers + one dialog, `main.py` = orchestration) and extend it:

- **`settings.py`** (new) — settings load/save/defaults, as in §2.
- **`gui.py`** (new) — all Tkinter UI beyond the existing `select_file()`: main window, settings dialog, progress bar, results panel, error dialogs.
- **`main.py`** (refactored) — extract the current `main()` body into a reusable `run_pipeline(p3_root: Path, excel_path: str, progress_callback=None) -> dict` (returns `{file_count, total_card_count, skip_count, elapsed, output_path}`), importable by `gui.py`. Keep a minimal `if __name__ == '__main__':` console path for developer debugging (fast iteration without launching Tkinter).
- **`app.py`** (new) — the literal PyInstaller entry point: `from gui import launch_app; launch_app()`.
- No changes needed to: `get_source_files()`, `load_excel()`, `detect_profile()`, `build_text()` (all `utils.py`), or `config.py`. `exceptions.py` classes are reused as-is, now caught at the `run_pipeline()` boundary in `gui.py` instead of via `sys.exit`.

## 6. Verification plan

- **Regression (source mode)**: run `run_pipeline()` against the sample data in `p3_PILOT HOME DELIVERY 20-05-2026/` via `python app.py`; confirm output `.p3` matches a pre-refactor baseline run, and card/skip counts in the results panel match `p3cc.log`.
- **Bug-fix verification**: confirm the `except Exception:` fix routes unexpected errors to the graceful error dialog (not a `TypeError`); confirm the `card_id` reset prevents cross-file data contamination with a deliberately malformed test `.p3` file.
- **Settings persistence**: delete `settings.json` → confirm defaults are created next to the exe on launch; run once → confirm remembered folders update; corrupt the JSON manually → confirm graceful fallback, not a crash.
- **Clean-machine packaged test**: copy only the built `dist/P3CC/` folder (plus a copy of the sample data folder) to a Windows machine/VM with **no Python installed**; confirm the app launches with no console flash, both pickers work, Run produces a correct output file, "Open output folder" works, and `settings.json` is written next to `P3CC.exe`.
- **Profile regression**: verify auto-detection still works through the GUI path for each of the three existing profiles (`yalla`, `classic`, `zamalek`) if sample Excel data covering more than one profile is available; otherwise flag as an untested gap rather than fabricating test data.

### Critical files
- `E:\Progamming_ideas\P3ccV2\main.py`
- `E:\Progamming_ideas\P3ccV2\utils.py`
- `E:\Progamming_ideas\P3ccV2\config.py` (unchanged, referenced for boundary)
- `E:\Progamming_ideas\P3ccV2\requirements.txt`
- `E:\Progamming_ideas\P3ccV2\run.bat` (dev-only going forward)
- New: `settings.py`, `gui.py`, `app.py`, `assets/p3cc.ico`, `requirements-dev.txt`