# P3CC (P3 Collect-Comparative)
**English** | [العربية](README-ar.md)

Developed by Eng. Mahmoud Al-Ansary
"ddph.it@egyptpost.org"


## Overview

P3CC is a Windows desktop tool that merges cardholder data from an Excel spreadsheet into `.p3` card-issuance files. It scans `.p3` source files for card-ID markers, looks up the matching Excel row, and injects tagged fields (cardholder name, national ID, mobile number, and other profile-specific data) into the output directly after the `#END#` marker of each card record, as a continuation of the same line.

It ships as a Tkinter GUI packaged into a standalone `P3CC.exe` (via PyInstaller) — end users need **no Python installed** and never touch a terminal.

The program is structured into these Python modules (source/dev mode only — none of this is required to run the packaged `.exe`):
- `app.py`: the GUI entry point — what PyInstaller packages into `P3CC.exe`.
- `gui.py`: the whole Tkinter UI — main window, Settings dialog, Manage Profiles dialog, progress bar, results panel, error dialogs.
- `main.py`: orchestrates file discovery, Excel loading, profile detection, and output generation via `run_pipeline()`. Also a minimal console entry point (`python main.py`) for developer debugging.
- `utils.py`: pure helper functions for data transformation, file handling, profile detection, and text building.
- `config.py`: developer-only constants — encoding, binary markers, the built-in default profile, and the pre-3.2 migration rules.
- `settings.py` / `field_map_store.py`: load and save the user-editable `settings.json` (remembered folders) and `field_map.json` (card profiles: identifying columns, card-ID column and Excel-column → `.p3`-tag fields) next to the running exe. `field_map_store.py` also validates, migrates, imports and resets profiles.
- `exceptions.py`: custom exception classes for specific error conditions, for precise error handling and clearer debugging.

## What's new in 3.2

- **Card profiles are now fully managed from the app.** A profile is a card type, for example `debit-cards`. Each one has a name, the Excel columns that identify it, the card-ID column, and its fields. All of this is stored in `field_map.json` and edited in the new **Manage Profiles** window (it replaces Manage Fields). You can add, rename or delete card types without a new program version. Before editing, read [Rules for editing profiles](#rules-for-editing-profiles-read-before-saving-any-change): some edits change the output that the card machines read.
- **Default profile is now `debit-cards`.** It replaces `classic` and covers all debit cards. It is identified by the `Card No` column. The `yalla` and `zamalek` profiles are retired.
- **Most specific profile wins.** When an Excel sheet matches more than one profile, the profile with the most identifying columns is chosen, whatever its position in the list. If two profiles match equally, the run stops with a clear message instead of guessing.
- **Test with Excel File.** In Manage Profiles, pick an Excel file to see which profile it selects and which field columns are missing, before running a batch.
- **Old `field_map.json` files are upgraded automatically.** Copy a `field_map.json` from an earlier version next to `P3CC.exe`, or use **Import…** in Manage Profiles. The upgrade keeps your field edits, renames `classic` to `debit-cards`, removes `yalla`/`zamalek`, and keeps the original as a `field_map.pre-3.2-backup-<date>.json` copy.
- **`field_map.json` problems are shown, never hidden.** Before 3.2, an unreadable file was silently replaced by the built-in defaults, so hand-edits seemed to be ignored. Now the app shows the error, including the line number for JSON syntax errors. It never overwrites the file on its own. Files saved by Notepad as "UTF-8 with BOM" are accepted. The app checks the file at startup, so a problem shows up right away.
- **Results panel shows the profile used** for each run.

## What's new in 3.1

- **Fix — card records containing line breaks are no longer damaged.** A card record (`<8-digit serial>"%B<16-digit card ID><encrypted data>#END#`) can contain CR, LF or CRLF bytes inside its encrypted data. Version 3.0 treated each line break as the start of a new line, so everything before the last line break of such a record was silently left out of the output file. Version 3.1 reads each record as one whole block, from its serial number through `#END#`, and copies it byte-for-byte. The Excel data is added only after `#END#`.
- **New — record layout checks.** Every record is checked for a valid header (8-digit serial, `"%B`, 16-digit card ID), consecutive serial numbers, a closing `#END#`, and signs of two records merged together. Problems are logged in `p3cc.log` with the file name and record number. Records with warnings are still written unchanged. Only an incomplete record (no `#END#`) is skipped.
- **New — lines outside card records are removed and logged.** Blank lines, header/footer text or any other line that is not part of a card record is left out of the output. Each removal is logged with its file name, line number and size, never its content.
- **Changed — output file name.** The output file is now named after the first source file with `_processed` added (e.g. `cards_01.p3` produces `cards_01_processed.p3`) instead of after the folder. All source files are still merged into this one file. Files ending in `_processed.p3` are skipped as input, so running the same folder again never re-reads a previous output. **Delete any old 3.0 output file (named after the folder, e.g. `My_P3_Files.p3`) from the folder before running 3.1**, otherwise it is read as a source file and its records are duplicated.
- **Results panel:** shows two new counts, **Layout warnings** and **Lines discarded**. Both should be 0 for a clean batch. If either isn't, check `p3cc.log` for details.

## Features

- **Portable, no-install packaging**: runs as `dist/P3CC/P3CC.exe` on any Windows machine, no Python required. Distribute the whole `P3CC` folder as a unit, not just the `.exe`.
- **Profile-based processing**: automatically detects the card type (profile, e.g. `debit-cards`) from the Excel sheet's columns, the most specific match winning, and applies that profile's field mapping.
- **Efficient data lookup**: uses pandas DataFrames with indexed lookups for fast retrieval of card data.
- **Arabic character normalization**: normalizes Eastern Arabic-Indic digits and a couple of special codepoints for `cp1256`-safe output.
- **User-managed profiles and fields**: the GUI's "Manage Profiles" dialog lets you add, rename and delete card types, set the columns that identify them, test an Excel file against them, and add/edit/delete/reorder each profile's Excel-column → `.p3`-tag fields. No code change is needed when card types or Excel columns change.
- **Remembered folders**: the Settings dialog remembers your last-used source and Excel folders.
- **Card data integrity**: each card record is copied byte-for-byte as one block, including any line breaks inside its encrypted data. The Excel data is appended right after `#END#`.
- **Record layout checks**: malformed headers, serial-number gaps, missing `#END#` and merged records are reported in `p3cc.log`.
- **Progress tracking and results panel**: a progress bar during processing, then a summary (profile used, files processed, cards read/written/skipped, layout warnings, lines discarded, elapsed time, output path) with an "Open Output Folder" button.
- **Logging**: detailed logging to `p3cc.log` next to the app for traceability and debugging.

## How to Use (end users)

1. Get the `P3CC` folder (containing `P3CC.exe` and its supporting files) — copy the whole folder, not just the `.exe`.
2. Double-click `P3CC.exe`.
3. **Choose Folder…** — pick the folder containing your `.p3` source files.
4. **Choose File…** — pick your Excel data file (`.xlsx` or `.xls`).
5. Click **Run**. A progress bar tracks the batch; when it finishes you'll see a results summary and an **Open Output Folder** button.
6. The output `.p3` file is written into the same folder as your source files, named after the first source file with `_processed` added (e.g. `cards_01.p3` produces `cards_01_processed.p3`). All source files in the folder are still merged into this one output file.

Use **Settings** to change the default folders the two file pickers open to. Use **Manage Profiles** to manage card types and which Excel column feeds which `.p3` tag, without touching any code — see [Profiles & field mappings](#profiles--field-mappings-manage-profiles-dialog) below.

## Running from source (developers)

```bash
git clone https://github.com/nasermaher/p3-collect-comparative.git   # get the source
cd p3-collect-comparative
pip install -r requirements-dev.txt   # runtime deps + pyinstaller
python app.py                         # run the GUI
python main.py                        # console entry point for pipeline debugging (still uses Tk file dialogs)
toolkit.bat                           # menu-driven wrapper: run / test / check / setup / package
```

See `CLAUDE.md` for the full architecture notes, build instructions, and the `.p3` file format details.

## Profiles & field mappings (Manage Profiles dialog)

A **profile** is a card type. Each profile has:
- a **name** (e.g. `debit-cards`);
- **identifying columns**: Excel columns that must ALL be present for this profile to be selected (e.g. `Card No`). To tell a new card type apart, give it a column only that type's Excel sheet has;
- a **card-ID column**: the Excel column holding the card number, matched against the card ID in the `.p3` records;
- its **fields**: which Excel column feeds which `.p3` tag, in output order.

When an Excel sheet matches several profiles, the one with the most identifying columns wins. If two match equally, the run stops and asks you to make them distinguishable.

Everything is edited from the GUI, not in code:

1. Open **Manage Profiles** from the main window.
2. **Test with Excel File…** (recommended first): shows which profile a sheet selects, warns about field columns the sheet doesn't have, and loads the sheet's column names into the dropdowns.
3. Pick a profile from the dropdown, or create one with **New…**. Use **Edit…** to rename it or change its identifying columns and card-ID column. Use **Delete** to remove it (at least one profile must remain).
4. **Add Field…** / **Edit Field…**: give the field a tag (e.g. `<address>`), a value source (an Excel column, a comma-separated fallback list, the running card counter, or empty), and an optional transform (strip blank/N-A values, normalize Arabic characters, or append `.JPG`). **Move Up** / **Move Down** reorder fields and **Delete Field** removes one.
5. **Import…** loads profiles from another `field_map.json`, including one from an older version, which is upgraded on the way in. **Reset All to Defaults** restores the built-in `debit-cards` profile. Both apply only when you save.
6. **Save & Close** checks everything first: no duplicate names, no two profiles with the same identifying columns, a card-ID column wherever identifying columns are set. Only then does it write `field_map.json` next to the exe. Changes take effect on the next Run, with no restart needed.

`field_map.json` can also be edited by hand (save it as UTF-8). If it can't be read, the app tells you why and leaves the file as it is. Manage Profiles then offers to reset it, keeping a backup copy.

## Rules for editing profiles (read before saving any change)

The card machines read P3CC's output file. Some profile edits change that output, so the machine's own settings must match them exactly. Follow these rules for every change.

#### What reaches the machine, and what doesn't

| Setting | Appears in the output file? | Effect of a change |
|---|---|---|
| Field **tags**, their **order**, their **values** | **Yes** | The machine's profile must be changed to match, **at the same time** |
| Profile **name** | No (only in the log and results panel) | None on the machine |
| **Identifying columns**, **card-ID column** | No | Only which profile is chosen, and which Excel row is matched to each card |

Each card record in the output looks like this, all on one line:
```
...#END#<arabic>NAME<national>29001011234567<postoffice>...<IssuanceDate>2026-05-20<cpf>1<EOR>
```

#### Tags
- Copy each tag **exactly** as it is configured on the machine, including the angle brackets: `<IssuanceDate>`. Tags are case-sensitive: `<IssuanceDate>`, `<issuancedate>` and `<Issuance Date>` are three different tags to the machine.
- Don't put spaces inside a tag.
- **Save & Close** and the field editor refuse a malformed tag (missing `< >`, a space inside, or `<cpf>`/`<EOR>`) and say why. They can't know the machine's exact tag names, though, so checking those is still up to you.
- Don't add `<cpf>1<EOR>`. P3CC adds it automatically at the end of every card.
- The **order** of the fields in Manage Profiles is the order written to the output. Use **Move Up** / **Move Down** to match the order the machine expects.
- A tag the machine needs but that has no Excel data still has to be listed. Use the value source **Empty (no value)**.

#### Profile names
- Use short English names in lowercase, with words joined by `-`, describing the card type: `debit-cards`, `prepaid-cards`, `payroll-cards`.
- Don't rename a profile without a reason. The name doesn't change the output, but it is what everyone sees in results and logs.

#### Excel column names
- Type column names **exactly** as they appear in the Excel header. Spaces at the start or end are ignored. Capital letters and Arabic letter forms are not: `الإسم` and `الاسم` are different. If a customer's sheets spell a column in more than one way, list all spellings separated by commas (a fallback list). The first one found is used.
- **Don't name a column so that it starts with `Col` or `Unn`** (for example `Color` or `Collection Date`). P3CC drops such columns when loading Excel, because those prefixes belong to blank auto-generated columns.
- **Identifying columns:** choose columns that only this card type's sheet has. If two profiles' sheets share the same columns, add a column unique to each. Otherwise the run stops with "matches several profiles equally".

#### The card-ID column
- In Excel, the card-number column must be formatted as **Text**. Excel stores numbers with only 15 significant digits, so a 16-digit card number stored as a Number loses its last digit (`1234567890123456` becomes `1234567890123450`). P3CC then can't match it, and the card is skipped.

#### Values
- The output file uses Arabic Windows encoding (`cp1256`). Characters it can't represent are written as `?`. For Arabic text fields, choose the transform **Arabic character normalize**. It also converts Eastern Arabic digits (٠١٢…) to 0-9.
- **Strip blank / N-A values** removes extra spaces around values such as national ID numbers.

#### Step by step, for every change
1. **Back up:** copy the current `field_map.json` (next to `P3CC.exe`) and add the date to the copy's name.
2. Make the change in **Manage Profiles**, then **Save & Close**.
3. **Test with Excel File…** on a real sheet. Check that the right profile is chosen and no field columns are missing.
4. Run a **small batch** and load the output on the machine. Confirm it reads every field correctly.
5. **Every PC that runs P3CC has its own `field_map.json`.** Copy the same final file next to `P3CC.exe` on each of them, or load it with **Import…**. Profiles that differ between PCs produce different output.
6. Keep a short change log: date, what changed, and the matching change on the machine.

## Configuration for developers (`config.py`)

`config.py` holds the constants that define the output data contract — a wrong edit here can silently corrupt card output, so it's a developer-only change, not something exposed in the GUI.

#### 1. `ENCODING`
- **Purpose**: character encoding for reading and writing `.p3` files.
- **Value**: `ENCODING = 'cp1256'` (common for Arabic Windows environments).

#### 2. `CARD_FILE_EXT`
- **Purpose**: file extension for the card data files.
- **Value**: `CARD_FILE_EXT = 'p3'`.

#### 3. `DEFAULT_PROFILES`
- **Purpose**: the built-in seed data: what a fresh install's `field_map.json` starts from, and what **Reset All to Defaults** restores. Day-to-day profile changes are made in the GUI and stored in `field_map.json`, not here.
- **Shape**: each profile is `{'name', 'signatures', 'lookup_col', 'fields'}`. Each field is `{'tag', 'column', 'processor'}`:
    - **`tag`**: the tag written to the `.p3` file (e.g. `'<arabic>'`).
    - **`column`**: an Excel column name, a list of fallback column names (first found wins), `None` (tag written empty), or `LINE_COUNT_SENTINEL` (`'__line_count__'`, injects the running card counter).
    - **`processor`**: `'col_check'` (strips/NaN-guards), `'chr_replace'` (normalizes Arabic characters), `'jpg'` (appends `.JPG`), or `None` for a plain string conversion.
- **Current default**:
```python
DEFAULT_PROFILES = [
    {
        'name': 'debit-cards',
        'signatures': ['Card No'],
        'lookup_col': 'Card No',
        'fields': [
            {'tag': '<arabic>',       'column': 'CardHolder Name',   'processor': None},
            {'tag': '<national>',     'column': 'NID',               'processor': 'col_check'},
            {'tag': '<postoffice>',   'column': 'Post Office Name2', 'processor': None},
            {'tag': '<region>',       'column': 'Post Region',       'processor': 'col_check'},
            {'tag': '<barcode>',      'column': 'Barcode',           'processor': None},
            {'tag': '<IssuanceDate>', 'column': 'Issue Date',        'processor': None},
        ],
    },
]
```

#### 4. `LEGACY_PROFILE_RENAMES` / `RETIRED_PROFILES`
- **Purpose**: how a pre-3.2 `field_map.json` is upgraded. `LEGACY_PROFILE_RENAMES = {'classic': 'debit-cards'}` renames a profile, keeping its fields and taking its identifying columns from the default of the new name. `RETIRED_PROFILES = ('yalla', 'zamalek')` are dropped (they remain in the backup copy). Any other old profile is kept with no identifying columns until the user sets them.

The resulting `field_map.json` format:
```json
{
  "version": 2,
  "profiles": [
    {"name": "debit-cards", "signatures": ["Card No"], "lookup_col": "Card No",
     "fields": [{"tag": "<arabic>", "column": "CardHolder Name", "processor": null}]}
  ]
}
```

## Error Handling (`exceptions.py`)

`exceptions.py` defines custom exception classes used throughout P3CC for specific error conditions, allowing precise error handling and clearer, more descriptive messages.

- **`P3CCError`**: base exception for all custom errors in P3CC. All other custom exceptions inherit from this.
- **`ProfileDetectionError`**: raised when no profile's identifying columns are all present in the Excel file, or when several profiles match it equally.
- **`SourceFilesError`**: raised when no `.p3` source files are found in the selected directory.
- **`MissingColumnError`**: raised when the detected profile's card-ID column is missing from the Excel data.
- **`FieldMapError`**: raised when `field_map.json` can't be read (bad JSON, wrong encoding) or fails validation. The message names the problem; the file is never silently replaced.
- **`InvalidCardError`**: raised when card data is found to be malformed or does not meet expected criteria during processing.

## Project Structure

```
p3cc/
├── app.py               # GUI entry point — what PyInstaller packages
├── gui.py                # Tkinter GUI: main window, Settings, Manage Profiles
├── main.py               # Pipeline orchestration + console dev entry point
├── utils.py               # Pure helper functions
├── config.py              # Developer-only constants, default profile, migration rules
├── settings.py            # settings.json load/save
├── field_map_store.py     # field_map.json profiles: load/validate/migrate/save
├── exceptions.py          # Custom exception definitions
├── P3CC.spec              # PyInstaller build spec (committed — preserves hidden-import fixes)
├── requirements.txt       # Runtime dependencies
├── requirements-dev.txt   # Runtime deps + PyInstaller (for building the exe)
├── run.bat                # Dev-only: activates .venv, quick-launches python app.py
├── toolkit.bat            # Menu-driven wrapper: run / test / check / setup / package
└── README.md              # This documentation
```
