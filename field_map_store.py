# ── field_map_store.py ───────────────────────────────────────────────────────
# User-editable Excel-column → p3-tag field mappings, per profile.
#
# Business needs (per profile) change over time — new Excel columns get added
# or dropped and need a matching p3 tag. That used to require a developer to
# edit config.FIELD_MAP; now it lives in field_map.json next to the app and is
# editable from the GUI's "Manage Fields" dialog.
#
# config.FIELD_MAP still exists as the built-in seed/reset data — it is what
# a fresh install starts from, and what "Reset to defaults" restores.
#
# PROFILE_SIGNATURES (which Excel layout selects which profile) is NOT
# user-editable here — inventing a wrong signature breaks auto-detection for
# every user of that profile, so that stays a developer change in config.py.
# ──────────────────────────────────────────────────────────────────────────────

import json
import logging
from pathlib import Path

import config
from settings import get_app_dir

log = logging.getLogger(__name__)

FIELD_MAP_FILENAME = 'field_map.json'


def _path() -> Path:
    return get_app_dir() / FIELD_MAP_FILENAME


def default_field_map() -> dict:
    """The built-in seed/reset data, converted from config.FIELD_MAP's tuples
    into the JSON-friendly dict shape used everywhere else in this module."""
    return {
        profile: [
            {'tag': tag, 'column': col_def, 'processor': processor_key}
            for tag, col_def, processor_key in fields
        ]
        for profile, fields in config.FIELD_MAP.items()
    }


def load_field_map() -> dict:
    """
    Load field_map.json, seeding it from config.FIELD_MAP on first run and
    falling back to those same built-in defaults if the file is missing or
    corrupt — a bad edit or a deleted file should never stop the app.
    """
    path = _path()
    if not path.exists():
        data = default_field_map()
        save_field_map(data)
        return data

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or not data:
            raise ValueError('file is empty or not a JSON object')
        return data
    except (json.JSONDecodeError, OSError, ValueError) as e:
        log.warning('Could not read %s (%s) — using built-in defaults.', path, e)
        return default_field_map()


def save_field_map(data: dict) -> None:
    """Write field_map.json next to the app. Logs (does not raise) on failure."""
    path = _path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        log.warning('Could not write %s: %s', path, e)


def profile_names() -> list[str]:
    """Profiles available to edit — config.PROFILE_SIGNATURES is the source
    of truth for which profiles exist at all."""
    return list(config.PROFILE_SIGNATURES.keys())
