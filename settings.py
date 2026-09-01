# ── settings.py ───────────────────────────────────────────────────────────────
# User-editable, day-to-day settings for P3CC — separate from config.py's
# business-logic constants. Stored as settings.json next to the running
# executable (or next to this script in source mode) so the whole app folder
# stays portable across machines and removable drives.
# ──────────────────────────────────────────────────────────────────────────────

import sys
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SETTINGS_FILENAME = 'settings.json'

DEFAULT_SETTINGS = {
    'last_source_folder': '.',
    'last_excel_folder': '.',
}


def get_app_dir() -> Path:
    """
    Directory the app's own files live in — the exe's folder when frozen
    by PyInstaller (--onedir), or this script's folder in source mode.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def get_resource_path(filename: str) -> Path:
    """
    Directory for read-only files bundled into the build (e.g. README.md, via
    P3CC.spec's `datas`) — PyInstaller's `sys._MEIPASS`, or this script's
    folder in source mode. Distinct from get_app_dir(): that one is for
    user-writable files that must sit next to the exe for the app folder to
    stay portable; bundled resources live wherever PyInstaller placed them.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / filename
    return Path(__file__).parent / filename


def _settings_path() -> Path:
    return get_app_dir() / SETTINGS_FILENAME


def load_settings() -> dict:
    """
    Load settings.json, falling back to defaults on any missing/corrupt file.
    Never raises — a bad settings file should not stop the app from starting.
    """
    path = _settings_path()
    if not path.exists():
        save_settings(DEFAULT_SETTINGS)
        return dict(DEFAULT_SETTINGS)

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError('settings.json is not a JSON object')
        merged = dict(DEFAULT_SETTINGS)
        merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
        return merged
    except (json.JSONDecodeError, OSError, ValueError) as e:
        log.warning('Could not read %s (%s) — using defaults.', path, e)
        save_settings(DEFAULT_SETTINGS)
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    """Write settings.json next to the app. Logs (does not raise) on failure."""
    path = _settings_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except OSError as e:
        log.warning('Could not write %s: %s', path, e)
