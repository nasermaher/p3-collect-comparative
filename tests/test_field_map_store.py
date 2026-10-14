import json

import pytest

import config
import field_map_store
from exceptions import FieldMapError


def profile(name='debit-cards', signatures=('Card No',), lookup_col='Card No', fields=None):
    return {
        'name': name,
        'signatures': list(signatures),
        'lookup_col': lookup_col,
        'fields': fields if fields is not None else [{'tag': '<x>', 'column': 'X', 'processor': None}],
    }


def write_raw(app_dir, content: str, encoding='utf-8'):
    (app_dir / 'field_map.json').write_text(content, encoding=encoding)


# ── Defaults & round trip ────────────────────────────────────────────────────


def test_default_profiles_is_debit_cards_only_and_valid():
    defaults = field_map_store.default_profiles()

    assert [p['name'] for p in defaults] == ['debit-cards']
    assert defaults[0]['signatures'] == ['Card No']
    assert field_map_store.validate_profiles(defaults) == []


def test_default_profiles_returns_independent_copy():
    field_map_store.default_profiles()[0]['fields'].clear()

    assert config.DEFAULT_PROFILES[0]['fields']


def test_load_seeds_defaults_when_file_missing(app_dir):
    profiles, notice = field_map_store.load_profiles_report()

    assert profiles == field_map_store.default_profiles()
    assert notice is None
    saved = json.loads((app_dir / 'field_map.json').read_text(encoding='utf-8'))
    assert saved['version'] == field_map_store.FORMAT_VERSION


def test_save_then_load_round_trips_profiles(app_dir):
    data = [profile(), profile('prepaid', ['Card No', 'Wallet ID'])]

    field_map_store.save_profiles(data)

    assert field_map_store.load_profiles() == data


def test_save_refuses_invalid_profiles_and_keeps_existing_file(app_dir):
    field_map_store.save_profiles([profile()])
    before = (app_dir / 'field_map.json').read_text(encoding='utf-8')

    with pytest.raises(FieldMapError):
        field_map_store.save_profiles([profile(), profile()])   # duplicate name

    assert (app_dir / 'field_map.json').read_text(encoding='utf-8') == before


# ── Unreadable files are reported, never silently replaced ──────────────────


@pytest.mark.parametrize('content', ['{not valid json', 'null', '[]', '{}', '{"profiles": "x"}'])
def test_load_raises_on_corrupt_file_and_leaves_it_untouched(app_dir, content):
    write_raw(app_dir, content)

    with pytest.raises(FieldMapError):
        field_map_store.load_profiles()

    assert (app_dir / 'field_map.json').read_text(encoding='utf-8') == content


def test_load_reports_json_syntax_error_line(app_dir):
    write_raw(app_dir, '{\n  "version": 2,\n  "profiles": [,]\n}')

    with pytest.raises(FieldMapError, match='line 3'):
        field_map_store.load_profiles()


def test_load_accepts_utf8_bom_written_by_notepad(app_dir):
    content = json.dumps({'version': 2, 'profiles': [profile()]})
    write_raw(app_dir, content, encoding='utf-8-sig')

    assert field_map_store.load_profiles() == [profile()]


def test_load_rejects_non_utf8_file_with_clear_message(app_dir):
    content = json.dumps({'version': 2, 'profiles': [profile(signatures=['رقم'])]}, ensure_ascii=False)
    write_raw(app_dir, content, encoding='cp1256')

    with pytest.raises(FieldMapError, match='UTF-8'):
        field_map_store.load_profiles()


# ── Validation ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(('profiles', 'expected'), [
    ([], 'at least one profile'),
    ([profile(name='')], '"name" must be non-empty'),
    ([profile(), profile(name='DEBIT-CARDS', signatures=['Other'])], 'more than one profile'),
    ([profile(lookup_col='')], 'card-ID column'),
    ([profile(), profile('b')], 'same identifying columns'),
    ([profile(signatures=[])], 'No profile has identifying columns'),
    ([profile(fields=[{'tag': '', 'column': 'X', 'processor': None}])], 'tag must be non-empty'),
    ([profile(fields=[{'tag': '<x>', 'column': '', 'processor': None}])], '"column" must be'),
    ([profile(fields=[{'tag': '<x>', 'column': 'X', 'processor': 'nope'}])], 'unknown processor'),
])
def test_validate_profiles_reports_problem(profiles, expected):
    problems = field_map_store.validate_profiles(profiles)

    assert any(expected in p for p in problems), problems


@pytest.mark.parametrize('tag', ['<IssuanceDate>', '<paymentDate><paymentNo>', '<VisaCardNo>', '<الاسم>'])
def test_tag_problem_accepts_well_formed_tags(tag):
    assert field_map_store.tag_problem(tag) is None


@pytest.mark.parametrize(('tag', 'expected'), [
    ('IssuanceDate', 'not a valid tag'),          # no brackets
    ('<Issuance Date>', 'not a valid tag'),       # space inside
    ('<IssuanceDate', 'not a valid tag'),         # unclosed
    ('<a><b', 'not a valid tag'),
    ('<>', 'not a valid tag'),
    (' <x> ', 'not a valid tag'),                 # surrounding spaces would reach the output
    ('<cpf>', 'must not include <cpf>'),
    ('<x><EOR>', 'must not include <EOR>'),
    ('   ', 'must be non-empty'),
])
def test_tag_problem_rejects_malformed_or_reserved_tags(tag, expected):
    assert expected in field_map_store.tag_problem(tag)


def test_save_rejects_malformed_tag(app_dir):
    with pytest.raises(FieldMapError, match='not a valid tag'):
        field_map_store.save_profiles([profile(fields=[{'tag': 'Barcode', 'column': 'X', 'processor': None}])])


def test_validate_allows_profile_without_signatures_alongside_detectable_one():
    # A profile with no identifying columns is allowed (never auto-detected),
    # as long as some other profile can be detected.
    assert field_map_store.validate_profiles([profile(), profile('draft', signatures=[], lookup_col='')]) == []


def test_validate_accepts_fallback_list_counter_and_empty_columns():
    fields = [
        {'tag': '<a>', 'column': ['A', 'B'], 'processor': 'col_check'},
        {'tag': '<n>', 'column': config.LINE_COUNT_SENTINEL, 'processor': None},
        {'tag': '<e>', 'column': None, 'processor': None},
    ]
    assert field_map_store.validate_profiles([profile(fields=fields)]) == []


# ── Migration of pre-3.2 files ──────────────────────────────────────────────

LEGACY = {
    'yalla': [{'tag': '<y>', 'column': 'Y', 'processor': None}],
    'classic': [{'tag': '<custom>', 'column': 'Custom Col', 'processor': 'col_check'}],
    'zamalek': [{'tag': '<z>', 'column': 'Z', 'processor': 'jpg'}],
    'my-type': [{'tag': '<m>', 'column': 'M', 'processor': None}],
}


def test_migrate_legacy_renames_classic_drops_retired_and_keeps_unknown():
    profiles, notice = field_map_store.migrate_legacy(LEGACY)

    by_name = {p['name']: p for p in profiles}
    assert set(by_name) == {'debit-cards', 'my-type'}
    # classic's hand-edited fields are kept under the new name, with its identifying columns
    assert by_name['debit-cards']['fields'] == LEGACY['classic']
    assert by_name['debit-cards']['signatures'] == ['Card No']
    assert by_name['debit-cards']['lookup_col'] == 'Card No'
    # an unknown profile is kept, but never auto-detected until the user sets its columns
    assert by_name['my-type']['signatures'] == []
    assert 'classic → debit-cards' in notice
    assert 'yalla, zamalek' in notice
    assert 'my-type' in notice


def test_migrate_legacy_adds_defaults_when_nothing_detectable_remains():
    profiles, notice = field_map_store.migrate_legacy({'yalla': LEGACY['yalla']})

    assert [p['name'] for p in profiles] == ['debit-cards']
    assert 'Added from defaults' in notice


def test_load_migrates_legacy_file_saves_v2_and_backs_up_original(app_dir):
    original = json.dumps(LEGACY, ensure_ascii=False)
    write_raw(app_dir, original)

    profiles, notice = field_map_store.load_profiles_report()

    assert [p['name'] for p in profiles] == ['debit-cards', 'my-type']
    assert 'pre-3.2-backup' in notice
    saved = json.loads((app_dir / 'field_map.json').read_text(encoding='utf-8'))
    assert saved == {'version': 2, 'profiles': profiles}
    backups = list(app_dir.glob('field_map.pre-3.2-backup-*.json'))
    assert len(backups) == 1
    assert backups[0].read_text(encoding='utf-8') == original
    # second load: already v2, nothing more to report
    assert field_map_store.load_profiles_report() == (profiles, None)


def test_read_field_map_file_imports_legacy_without_saving(app_dir, tmp_path):
    old = tmp_path / 'old_field_map.json'
    old.write_text(json.dumps(LEGACY), encoding='utf-8')

    profiles, notice = field_map_store.read_field_map_file(old)

    assert 'debit-cards' in [p['name'] for p in profiles]
    assert notice
    assert not (app_dir / 'field_map.json').exists()


# ── Reset ───────────────────────────────────────────────────────────────────


def test_reset_to_defaults_backs_up_broken_file(app_dir):
    write_raw(app_dir, '{broken')

    backup = field_map_store.reset_to_defaults()

    assert backup.read_text(encoding='utf-8') == '{broken'
    assert field_map_store.load_profiles() == field_map_store.default_profiles()
