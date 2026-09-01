# ── utils.py ──────────────────────────────────────────────────────────────────
# Pure helper functions for P3CC.  - Version 3.0
# No I/O, no sys.exit(), no file paths — only data transformations.
# Every function here is independently testable.
# ──────────────────────────────────────────────────────────────────────────────

import logging
from typing import Callable

import pandas as pd
import xlrd  # noqa: F401 — pandas.read_excel() only imports this lazily for .xls
             # files, so PyInstaller's static analysis misses it; importing it here
             # directly makes the packaged build actually bundle it.
from pathlib import Path
from tkinter import filedialog

import field_map_store
from exceptions import ProfileDetectionError, SourceFilesError, MissingColumnError
from config import (
    CARD_FILE_EXT,
    PROFILE_SIGNATURES,
    NORMALIZATION_TABLE,
)

log = logging.getLogger(__name__)

# ── Value processors ──────────────────────────────────────────────────────────

def _plain(val) -> str:
    """Default processor — stringify without modification."""
    return str(val)


def _checked(val: str) -> str:
    """Return empty string for NaN/None/NaT; otherwise stringify and strip."""
    if pd.isna(val):
        return ''
    return str(val).strip()


def _replaced(string: str) -> str:
    """
    Normalize Arabic characters in a string:
      1. Replace any char with codepoint > 65381 with '_' (pre-pass, list comp).
      2. Apply NORMALIZATION_TABLE via str.translate() (C-speed, single pass).
    """
    pre_cleaned = ['_' if ord(c) > 65381 else c for c in string]
    return ''.join(pre_cleaned).translate(NORMALIZATION_TABLE)


def _jpg(val) -> str:
    """Processor: append .JPG extension."""
    return str(val) + '.JPG'

# ── Processor registry ────────────────────────────────────────────────────────
# Maps the string name stored in config.FIELD_MAP to the actual callable.
# config.py stores None for most fields; special fields store a string key.
# _normalize_field_map() resolves both at startup.

_PROCESSOR_REGISTRY: dict[str, Callable] = {
    'col_check':   _checked,
    'chr_replace': _replaced,
    'jpg':         _jpg,
}


# ── FIELD_MAP normalization ───────────────────────────────────────────────────

def get_resolved_field_map() -> dict:
    """
    Load the current (possibly user-edited via the GUI's Manage Fields dialog)
    field map from field_map_store and resolve processor keys to callables, so
    build_text() never branches on strings. Called once per pipeline run —
    not cached — so edits made between runs take effect without a restart.
    """
    raw = field_map_store.load_field_map()
    resolved = {}
    for profile, fields in raw.items():
        resolved[profile] = [
            (f['tag'], f.get('column'), _PROCESSOR_REGISTRY.get(f.get('processor'), _plain))
            for f in fields
        ]
    return resolved


# ── Row resolver ──────────────────────────────────────────────────────────────

def resolve_col(row: pd.Series, col_def: str | list[str] | None) -> str:
    """
    Resolve a col_def to a value from the given row.

      col_def = None        → '' (tag with no value, e.g. <address>)
      col_def = str         → row[col_def]
      col_def = list[str]   → first column name found in row.index
    """
    if col_def is None:
        return ''
    if isinstance(col_def, list):
        for name in col_def:
            if name in row.index:
                return row[name]
        raise KeyError(f'None of the fallback columns {col_def} found in row.')
    return row[col_def]


# ── Text builder ──────────────────────────────────────────────────────────────

def build_text(profile: str, row: pd.Series, line_count: int, resolved_field_map: dict) -> str:
    """
    Build the full tagged output string for one card row.

    Args:
        profile:            Active profile name ('yalla', 'zamalek', 'classic').
        row:                A pandas Series representing one Excel row.
        line_count:         Card counter — injected for fields marked '__line_count__'.
        resolved_field_map: Result of get_resolved_field_map(), passed in so it's
                             loaded once per batch rather than once per card.

    Returns:
        Encoded tag string ending with <cpf>1<EOR>\\r\\n
    """
    parts = []
    for tag, col_def, processor in resolved_field_map[profile]:
        value = line_count if col_def == '__line_count__' else resolve_col(row, col_def)
        parts.append(tag + processor(value))
    parts.append('<cpf>1<EOR>\r\n')
    return ''.join(parts)


# ── Profile detection ─────────────────────────────────────────────────────────

def detect_profile(columns) -> tuple[str, str]:
    """
    Identify the active profile from Excel column names.

    Args:
        columns: pandas Index or list of column names.

    Returns:
        (profile_name, lookup_col) — the profile key and the card ID column.

    Raises:
        ProfileDetectionError: if no profile signature matches.
        MissingColumnError: if the matched profile's lookup_col is absent.
    """
    profile = None
    lookup_col = None

    # 1. Dynamically match the profile signature
    for prof_name, prof_def in PROFILE_SIGNATURES.items():
        # Checks if all required signature columns exist in the input columns
        if all(sig in columns for sig in prof_def['signatures']):
            profile = prof_name
            lookup_col = prof_def['lookup_col']
            break   # Exit loop once the first match is found
    # 2. No signature matched at all
    if profile is None:
        raise ProfileDetectionError('Unrecognized Excel structure — no matching profile found.')

    # 3. Matched profile, but its lookup column is missing from the sheet
    if lookup_col not in columns:
        raise MissingColumnError(
            f'Profile "{profile}" requires lookup column "{lookup_col}" — not found.'
        )

    return profile, lookup_col


# ── File selection dialog ─────────────────────────────────────────────────────

def select_file(title: str = 'Select file', folder: str = '.') -> str | None:
    """
    Open a native file-picker dialog.

    Args:
        title:  Dialog window title.
        folder: Initial directory shown in the dialog.

    Returns:
        Selected file path as string, or None if cancelled.

    Raises:
        FileNotFoundError if the initial folder does not exist.
    """
    if not Path(folder).is_dir():
        raise FileNotFoundError(f"The folder '{folder}' does not exist.")
    return filedialog.askopenfilename(title=title, initialdir=folder) or None


# ── Source file discovery ─────────────────────────────────────────────────────

def get_source_files(p3_root: Path, output_file: Path) -> list[str]:
    """
    Return a list of .p3 source file names in p3_root,
    excluding the output file to prevent it being read as input.

    Args:
        p3_root:     Directory containing the .p3 source files.
        output_file: The output .p3 path to exclude.

    Returns:
        List of file name strings (not full paths).

    Exits:
        raise SourceFilesError() if no source files are found.
    """
    files = [f.name for f in p3_root.glob(f'*.{CARD_FILE_EXT}') if f != output_file]
    if not files:
        raise SourceFilesError(f'No .{CARD_FILE_EXT} source files found in {p3_root}')
    return files


# ── Excel loader ──────────────────────────────────────────────────────────────

def load_excel(path: str) -> pd.DataFrame:
    """
    Load an Excel file into a DataFrame.
      - Reads all columns as strings (dtype=str).
      - Strips leading/trailing spaces from column headers.
      - Drops auto-generated columns whose names start with 'Col' or 'Unn'.

    Args:
        path: Path to the Excel file.

    Returns:
        Cleaned pandas DataFrame.
    """
    df = pd.read_excel(path, dtype=str)
    df.columns = df.columns.str.strip()
    df = df.loc[:, ~df.columns.str[:3].isin(['Col', 'Unn'])]
    return df
