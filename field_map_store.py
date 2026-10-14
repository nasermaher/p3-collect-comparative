# ── field_map_store.py ───────────────────────────────────────────────────────
# User-editable card profiles: which Excel layout identifies each card type,
# which column holds the card ID, and which Excel columns feed which .p3 tags.
#
# Business needs change over time — card types get added, retired or renamed,
# and Excel columns come and go. All of that lives in field_map.json next to
# the app and is editable from the GUI's "Manage Profiles" dialog; nothing
# about profiles is hardcoded. config.DEFAULT_PROFILES is only the seed for a
# fresh install and what "Reset All to Defaults" restores.
#
# File format (version 2):
#   {"version": 2, "profiles": [{"name", "signatures", "lookup_col", "fields"}]}
# Files from before 3.2 ({profile_name: [fields]}) are migrated automatically
# on load, after backing up the original.
#
# A file that can't be read or fails validation raises FieldMapError — it is
# never silently replaced with defaults, so a hand-edit is never lost.
# ──────────────────────────────────────────────────────────────────────────────

import copy
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path

import config
from exceptions import FieldMapError
from settings import get_app_dir
from utils import processor_keys

log = logging.getLogger(__name__)

FIELD_MAP_FILENAME = 'field_map.json'
FORMAT_VERSION = 2


def _path() -> Path:
    return get_app_dir() / FIELD_MAP_FILENAME


def default_profiles() -> list[dict]:
    """The built-in seed/reset profiles (a fresh copy, safe to mutate)."""
    return copy.deepcopy(config.DEFAULT_PROFILES)


# ── Validation ────────────────────────────────────────────────────────────────

# One or more <tag>s with no spaces or stray brackets, e.g. <IssuanceDate> or
# <paymentDate><paymentNo>. The card machines match tags character-for-character.
_TAG_RE = re.compile(r'(<[^<>\s]+>)+')
_RESERVED_TAGS = ('<cpf>', '<EOR>')      # appended automatically after every card


def tag_problem(tag) -> str | None:
    """Return why a field tag is invalid, or None if it's fine."""
    if not isinstance(tag, str) or not tag.strip():
        return 'must be non-empty text'
    if not _TAG_RE.fullmatch(tag):
        return (f'"{tag}" is not a valid tag — write it exactly as configured on the card machine, '
                'inside < >, with no spaces (e.g. <IssuanceDate>)')
    reserved = [r for r in _RESERVED_TAGS if r.lower() in tag.lower()]
    if reserved:
        return f'"{tag}" must not include {", ".join(reserved)} — P3CC adds <cpf>1<EOR> after every card itself'
    return None


def _field_problems(where: str, field) -> list[str]:
    if not isinstance(field, dict):
        return [f'{where}: must be an object with "tag", "column" and "processor".']
    problems = []
    tag_issue = tag_problem(field.get('tag'))
    if tag_issue:
        problems.append(f'{where}: tag {tag_issue}.')
    col = field.get('column')
    valid_col = (
        col is None
        or (isinstance(col, str) and col.strip())
        or (isinstance(col, list) and col and all(isinstance(c, str) and c.strip() for c in col))
    )
    if not valid_col:
        problems.append(f'{where}: "column" must be a column name, a list of column names, or null.')
    proc = field.get('processor')
    if proc is not None and proc not in processor_keys():
        problems.append(f'{where}: unknown processor "{proc}" (valid: {", ".join(processor_keys())} or null).')
    return problems


def validate_profiles(profiles) -> list[str]:
    """
    Check profiles for structural and logical problems. Returns a list of
    human-readable problems — empty means valid.
    """
    if not isinstance(profiles, list) or not profiles:
        return ['There must be at least one profile.']

    problems = []
    seen_names = set()
    seen_signatures = {}

    for i, p in enumerate(profiles, start=1):
        if not isinstance(p, dict):
            problems.append(f'Profile #{i}: must be an object.')
            continue
        name = p.get('name')
        label = f'Profile "{name}"' if isinstance(name, str) and name.strip() else f'Profile #{i}'

        if not isinstance(name, str) or not name.strip():
            problems.append(f'{label}: "name" must be non-empty text.')
        elif name.strip().lower() in seen_names:
            problems.append(f'{label}: the name is used by more than one profile.')
        else:
            seen_names.add(name.strip().lower())

        sigs = p.get('signatures')
        if not isinstance(sigs, list) or not all(isinstance(s, str) and s.strip() for s in sigs):
            problems.append(f'{label}: "signatures" (identifying columns) must be a list of column names.')
        elif sigs:
            key = frozenset(sigs)
            if key in seen_signatures:
                problems.append(f'{label}: has the same identifying columns as profile '
                                f'"{seen_signatures[key]}" — they can\'t be told apart.')
            else:
                seen_signatures[key] = name
            lookup = p.get('lookup_col')
            if not isinstance(lookup, str) or not lookup.strip():
                problems.append(f'{label}: "lookup_col" (card-ID column) must be set.')

        fields = p.get('fields')
        if not isinstance(fields, list):
            problems.append(f'{label}: "fields" must be a list.')
        else:
            for j, f in enumerate(fields, start=1):
                problems.extend(_field_problems(f'{label}, field #{j}', f))

    if not problems and not seen_signatures:
        problems.append('No profile has identifying columns, so no Excel sheet could ever be recognized.')
    return problems


# ── Parsing & migration ───────────────────────────────────────────────────────

def _is_legacy(data) -> bool:
    return (isinstance(data, dict) and 'profiles' not in data and bool(data)
            and all(isinstance(v, list) for v in data.values()))


def migrate_legacy(data: dict) -> tuple[list[dict], str]:
    """
    Convert a pre-3.2 {profile_name: [fields]} map into version-2 profiles.
    Returns (profiles, human-readable summary of what changed).
    """
    defaults = {p['name']: p for p in config.DEFAULT_PROFILES}
    profiles, renamed, retired, unidentified = [], [], [], []

    for old_name, fields in data.items():
        if old_name in config.RETIRED_PROFILES:
            retired.append(old_name)
            continue
        new_name = config.LEGACY_PROFILE_RENAMES.get(old_name, old_name)
        if new_name != old_name and new_name in data:
            new_name = old_name          # explicit profile of that name already exists
        if new_name != old_name:
            renamed.append(f'{old_name} → {new_name}')
        seed = defaults.get(new_name)
        if seed is None:
            unidentified.append(new_name)
        profiles.append({
            'name': new_name,
            'signatures': list(seed['signatures']) if seed else [],
            'lookup_col': seed['lookup_col'] if seed else '',
            'fields': fields,
        })

    added = []
    if not any(p['signatures'] for p in profiles):
        taken = {p['name'] for p in profiles}
        for p in default_profiles():
            if p['name'] not in taken:
                profiles.append(p)
                added.append(p['name'])

    notes = ['field_map.json was from a version before 3.2 and has been upgraded.']
    if renamed:
        notes.append(f'Renamed (fields kept): {", ".join(renamed)}.')
    if retired:
        notes.append(f'Removed retired profiles: {", ".join(retired)}.')
    if added:
        notes.append(f'Added from defaults: {", ".join(added)}.')
    if unidentified:
        notes.append(f'No identifying columns yet — set them in Manage Profiles: {", ".join(unidentified)}.')
    return profiles, ' '.join(notes)


def parse_field_map(data) -> tuple[list[dict], str | None]:
    """
    Turn loaded JSON (either format) into validated profiles.
    Returns (profiles, migration summary or None). Raises FieldMapError.
    """
    notice = None
    if _is_legacy(data):
        profiles, notice = migrate_legacy(data)
    elif isinstance(data, dict) and isinstance(data.get('profiles'), list):
        profiles = data['profiles']
    else:
        raise FieldMapError('Unrecognized structure — expected {"version": 2, "profiles": [...]}.')

    problems = validate_profiles(profiles)
    if problems:
        raise FieldMapError('\n'.join(problems))
    return profiles, notice


def read_field_map_file(path: Path) -> tuple[list[dict], str | None]:
    """
    Read and parse any field map file (accepts a UTF-8 BOM, as Notepad may
    write). Returns (profiles, migration summary or None). Raises
    FieldMapError naming the file and, for JSON syntax errors, the line.
    """
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise FieldMapError(f'{path}: invalid JSON at line {e.lineno}, column {e.colno} — {e.msg}.') from e
    except UnicodeDecodeError as e:
        raise FieldMapError(f'{path}: not UTF-8 text — save it as UTF-8 and try again.') from e
    except OSError as e:
        raise FieldMapError(f'{path}: could not be read — {e}.') from e

    try:
        return parse_field_map(data)
    except FieldMapError as e:
        raise FieldMapError(f'{path}:\n{e}') from e


# ── Load / save ───────────────────────────────────────────────────────────────

def _backup(path: Path, label: str) -> Path:
    """Copy path to <stem>.<label>-<timestamp>.json next to it; return the copy."""
    target = path.with_name(f'{path.stem}.{label}-{time.strftime("%Y%m%d-%H%M%S")}.json')
    shutil.copy2(path, target)
    return target


def load_profiles_report() -> tuple[list[dict], str | None]:
    """
    Load the profiles from field_map.json next to the app.

    - Missing file → seeded from the built-in defaults and saved.
    - Pre-3.2 file → original backed up, migrated, saved in the new format;
      the returned notice says what changed.
    - Unreadable/invalid file → FieldMapError; the file is left untouched.

    Returns (profiles, notice or None).
    """
    path = _path()
    if not path.exists():
        profiles = default_profiles()
        save_profiles(profiles)
        return profiles, None

    profiles, notice = read_field_map_file(path)
    if notice:
        backup = _backup(path, 'pre-3.2-backup')
        save_profiles(profiles)
        notice += f' The original file was saved as {backup.name}.'
        log.info(notice)
    return profiles, notice


def load_profiles() -> list[dict]:
    return load_profiles_report()[0]


def save_profiles(profiles: list[dict]) -> None:
    """
    Validate, then write field_map.json next to the app (via a temp file, so a
    failed write never leaves a half-written file). Raises FieldMapError.
    """
    problems = validate_profiles(profiles)
    if problems:
        raise FieldMapError('\n'.join(problems))

    path = _path()
    tmp = path.with_suffix('.tmp')
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'version': FORMAT_VERSION, 'profiles': profiles}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError as e:
        raise FieldMapError(f'Could not write {path}: {e}') from e


def reset_to_defaults() -> Path | None:
    """
    Replace field_map.json with the built-in defaults, backing up the current
    file first (even an unreadable one). Returns the backup path, if any.
    """
    path = _path()
    backup = _backup(path, 'backup') if path.exists() else None
    save_profiles(default_profiles())
    if backup:
        log.info('field_map.json reset to defaults; previous file saved as %s', backup.name)
    return backup
