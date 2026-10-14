# P3CC (P3 Collect-Comparative)
Developed by Eng. Mahmoud Al-Ansary
"ddph.it@egyptpost.org"


## Overview

P3CC is a Windows desktop tool that merges cardholder data from an Excel spreadsheet into `.p3` card-issuance files. It scans `.p3` source files for card-ID markers, looks up the matching Excel row, and injects tagged fields (cardholder name, national ID, mobile number, and other profile-specific data) into the output directly after the `#END#` marker of each card record, as a continuation of the same line.

It ships as a Tkinter GUI packaged into a standalone `P3CC.exe` (via PyInstaller) — end users need **no Python installed** and never touch a terminal.

The program is structured into these Python modules (source/dev mode only — none of this is required to run the packaged `.exe`):
- `app.py`: the GUI entry point — what PyInstaller packages into `P3CC.exe`.
- `gui.py`: the whole Tkinter UI — main window, Settings dialog, Manage Fields dialog, progress bar, results panel, error dialogs.
- `main.py`: orchestrates file discovery, Excel loading, profile detection, and output generation via `run_pipeline()`. Also a minimal console entry point (`python main.py`) for developer debugging.
- `utils.py`: pure helper functions for data transformation, file handling, profile detection, and text building.
- `config.py`: developer-only constants — encoding, binary markers, profile signatures, and the built-in seed/reset field mappings.
- `settings.py` / `field_map_store.py`: load and save the user-editable `settings.json` (remembered folders) and `field_map.json` (Excel-column → `.p3`-tag mappings) next to the running exe.
- `exceptions.py`: custom exception classes for specific error conditions, for precise error handling and clearer debugging.

## What's new in 3.1

- **Fix — card records containing line breaks are no longer damaged.** A card record (`<8-digit serial>"%B<16-digit card ID><encrypted data>#END#`) can contain CR, LF or CRLF bytes inside its encrypted data. Version 3.0 treated each line break as the start of a new line, so everything before the last line break of such a record was silently left out of the output file. Version 3.1 reads each record as one whole block, from its serial number through `#END#`, and copies it byte-for-byte. The Excel data is added only after `#END#`.
- **New — record layout checks.** Every record is checked for a valid header (8-digit serial, `"%B`, 16-digit card ID), consecutive serial numbers, a closing `#END#`, and signs of two records merged together. Problems are logged in `p3cc.log` with the file name and record number. Records with warnings are still written unchanged. Only an incomplete record (no `#END#`) is skipped.
- **New — lines outside card records are removed and logged.** Blank lines, header/footer text or any other line that is not part of a card record is left out of the output. Each removal is logged with its file name, line number and size, never its content.
- **Results panel:** shows two new counts, **Layout warnings** and **Lines discarded**. Both should be 0 for a clean batch. If either isn't, check `p3cc.log` for details.

## Features

- **Portable, no-install packaging**: runs as `dist/P3CC/P3CC.exe` on any Windows machine, no Python required. Distribute the whole `P3CC` folder as a unit, not just the `.exe`.
- **Profile-based processing**: automatically detects the Excel file structure (e.g., `yalla`, `zamalek`, `classic`) and applies the correct data mapping.
- **Efficient data lookup**: uses pandas DataFrames with indexed lookups for fast retrieval of card data.
- **Arabic character normalization**: normalizes Eastern Arabic-Indic digits and a couple of special codepoints for `cp1256`-safe output.
- **User-editable field mappings**: the GUI's "Manage Fields" dialog lets you add/edit/delete/reorder Excel-column → `.p3`-tag mappings per profile — no code change needed when a customer adds or drops an Excel column.
- **Remembered folders**: the Settings dialog remembers your last-used source and Excel folders.
- **Card data integrity**: each card record is copied byte-for-byte as one block, including any line breaks inside its encrypted data. The Excel data is appended right after `#END#`.
- **Record layout checks**: malformed headers, serial-number gaps, missing `#END#` and merged records are reported in `p3cc.log`.
- **Progress tracking and results panel**: a progress bar during processing, then a summary (files processed, cards read/written/skipped, layout warnings, lines discarded, elapsed time, output path) with an "Open Output Folder" button.
- **Logging**: detailed logging to `p3cc.log` next to the app for traceability and debugging.

## How to Use (end users)

1. Get the `P3CC` folder (containing `P3CC.exe` and its supporting files) — copy the whole folder, not just the `.exe`.
2. Double-click `P3CC.exe`.
3. **Choose Folder…** — pick the folder containing your `.p3` source files.
4. **Choose File…** — pick your Excel data file (`.xlsx` or `.xls`).
5. Click **Run**. A progress bar tracks the batch; when it finishes you'll see a results summary and an **Open Output Folder** button.
6. The output `.p3` file is written into the same folder as your source files, named after that folder (e.g. a folder named `My P3 Files` produces `My_P3_Files.p3`).

Use **Settings** to change the default folders the two file pickers open to. Use **Manage Fields** to add, edit, delete, or reorder which Excel column feeds which `.p3` tag for the active profile, without touching any code — see [Field mappings](#field-mappings-manage-fields-dialog) below.

## Running from source (developers)

```bash
pip install -r requirements-dev.txt   # runtime deps + pyinstaller
python app.py                         # run the GUI
python main.py                        # console entry point for pipeline debugging (still uses Tk file dialogs)
toolkit.bat                           # menu-driven wrapper: run / test / check / setup / package
```

See `CLAUDE.md` for the full architecture notes, build instructions, and the `.p3` file format details.

## Field mappings (Manage Fields dialog)

Day-to-day changes to which Excel column feeds which `.p3` tag are made from the GUI, not by editing code:

1. Open **Manage Fields** from the main window.
2. Pick the profile to edit from the dropdown.
3. **Add…** / **Edit…** a field: give it a tag (e.g. `<address>`), a value source (an Excel column, a comma-separated fallback list, the running card counter, or empty), and an optional transform (strip blank/N-A values, normalize Arabic characters, or append `.JPG`).
4. **Move Up** / **Move Down** to reorder, **Delete** to remove a field.
5. **Reset Profile to Defaults** restores the built-in mapping for that profile if you want to start over.
6. **Save & Close** writes the change to `field_map.json` next to the exe — it takes effect on the next Run, no restart needed.

## Configuration for developers (`config.py`)

`config.py` holds the constants that define the output data contract — a wrong edit here can silently corrupt card output, so it's a developer-only change, not something exposed in the GUI.

#### 1. `ENCODING`
- **Purpose**: character encoding for reading and writing `.p3` files.
- **Value**: `ENCODING = 'cp1256'` (common for Arabic Windows environments).

#### 2. `CARD_FILE_EXT`
- **Purpose**: file extension for the card data files.
- **Value**: `CARD_FILE_EXT = 'p3'`.

#### 3. `PROFILE_SIGNATURES`
- **Purpose**: maps a profile name to the Excel columns that must all be present to identify it, and which column is the card-ID lookup key. Dict order matters — the first matching profile wins.
- **How to add a profile**: add an entry with a `signatures` list and a `lookup_col`, then add a matching entry to `FIELD_MAP` below so there's seed data the first time someone opens Manage Fields for it.
- **Current profiles**:
```python
PROFILE_SIGNATURES = {
    'yalla': {
        'signatures': ['Card No', 'Mobile Number'],
        'lookup_col': 'Card No',
    },
    'classic': {
        'signatures': ['Card No'],
        'lookup_col': 'Card No',
    },
    'zamalek': {
        'signatures': ['رقم بطاقة الصراف الالى'],
        'lookup_col': 'رقم بطاقة الصراف الالى',
    },
    'my_new_profile': {
        'signatures': ['Unique Column A', 'Unique Column B'],
        'lookup_col': 'Unique Column A',
    },
}
```

#### 4. `FIELD_MAP`
- **Purpose**: the built-in seed data for each profile's field mappings — what a fresh install starts from, and what Manage Fields' "Reset to Defaults" restores. Each entry is a tuple: `(output_tag, col_def, processor_key)`.
    - **`output_tag`**: the tag written to the `.p3` file (e.g. `'<arabic>'`, `'<MobileNumber>'`).
    - **`col_def`**: an Excel column name (`str`), a list of fallback column names (first found wins), `None` (tag written empty), or `'__line_count__'` (injects the running card counter).
    - **`processor_key`**: a key into `utils.py`'s processor registry — `'col_check'` (strips/NaN-guards), `'chr_replace'` (normalizes Arabic characters), `'jpg'` (appends `.JPG`) — or `None` for a plain string conversion.
- **Example** — the real `yalla` profile:
```python
FIELD_MAP = {
    'yalla': [
        ('<arabic>', 'CardHolder Name', None),
        ('<national>', 'NID', 'col_check'),
        ('<postoffice>', 'Post Office Name2', 'chr_replace'),
        ('<region>', 'Post Region', 'col_check'),
        ('<barcode>', 'Barcode', None),
        ('<ClientNo>', 'Client No', None),
        ('<MobileNumber>', 'Mobile Number', None),
        ('<IssuanceDate>', 'Issue Date', None),
        ('<address>', 'Address', None),
        ('<city>', 'City', None),
    ],
    # 'classic' and 'zamalek' follow the same shape.
}
```

## Error Handling (`exceptions.py`)

`exceptions.py` defines custom exception classes used throughout P3CC for specific error conditions, allowing precise error handling and clearer, more descriptive messages.

- **`P3CCError`**: base exception for all custom errors in P3CC. All other custom exceptions inherit from this.
- **`ProfileDetectionError`**: raised when no profile signature in `PROFILE_SIGNATURES` matches the provided Excel file.
- **`SourceFilesError`**: raised when no `.p3` source files are found in the selected directory.
- **`MissingColumnError`**: raised when a required column (from `FIELD_MAP` or `PROFILE_SIGNATURES`) is missing from the Excel data.
- **`InvalidCardError`**: raised when card data is found to be malformed or does not meet expected criteria during processing.

## Project Structure

```
p3cc/
├── app.py               # GUI entry point — what PyInstaller packages
├── gui.py                # Tkinter GUI: main window, Settings, Manage Fields
├── main.py               # Pipeline orchestration + console dev entry point
├── utils.py               # Pure helper functions
├── config.py              # Developer-only constants, profile signatures, seed field map
├── settings.py            # settings.json load/save
├── field_map_store.py     # field_map.json load/save
├── exceptions.py          # Custom exception definitions
├── P3CC.spec              # PyInstaller build spec (committed — preserves hidden-import fixes)
├── requirements.txt       # Runtime dependencies
├── requirements-dev.txt   # Runtime deps + PyInstaller (for building the exe)
├── run.bat                # Dev-only: activates .venv, quick-launches python app.py
├── toolkit.bat            # Menu-driven wrapper: run / test / check / setup / package
└── README.md              # This documentation
```
