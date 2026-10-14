import pandas as pd
import pytest

import config
import utils
from exceptions import MissingColumnError, ProfileDetectionError, SourceFilesError

# ── Value processors ────────────────────────────────────────────────────────


@pytest.mark.parametrize('processor', [utils._plain, utils._checked, utils._jpg, utils._replaced])
@pytest.mark.parametrize('blank_value', [float('nan'), None, pd.NA])
def test_processor_returns_empty_string_for_blank_cell(processor, blank_value):
    # Regression: pandas.read_excel(dtype=str) still returns NaN for a genuinely empty cell, and
    # before this guard, _plain/_jpg/_replaced wrote the literal "nan"/"nan.JPG" into the .p3
    # output (or crashed, for _replaced iterating a float) instead of an empty tag value. Only
    # _checked guarded against this originally.
    assert processor(blank_value) == ''


def test_checked_strips_whitespace_from_real_value():
    assert utils._checked('  012345  ') == '012345'


def test_plain_stringifies_real_value_without_modification():
    assert utils._plain(42) == '42'


def test_jpg_appends_extension_to_real_value():
    assert utils._jpg('photo1') == 'photo1.JPG'


def test_replaced_normalizes_eastern_arabic_indic_digits():
    assert utils._replaced('١٢٣') == '123'


def test_replaced_replaces_high_codepoint_with_underscore():
    # U+FFFC (object replacement char) is the kind of invisible character a Word-paste can leave
    # behind in an Excel cell; anything above 65381 must degrade to '_' for cp1256-safe output.
    assert utils._replaced('safe￼unsafe') == 'safe_unsafe'


# ── resolve_col ──────────────────────────────────────────────────────────────


def test_resolve_col_returns_empty_string_when_coldef_is_none():
    row = pd.Series({'Name': 'Ali'})
    assert utils.resolve_col(row, None) == ''


def test_resolve_col_returns_value_for_string_coldef():
    row = pd.Series({'Name': 'Ali'})
    assert utils.resolve_col(row, 'Name') == 'Ali'


def test_resolve_col_returns_first_found_fallback_column():
    row = pd.Series({'اللـقـــب': 'Eng.'})
    assert utils.resolve_col(row, ['اللقب', 'اللـقـــب']) == 'Eng.'


def test_resolve_col_raises_keyerror_when_no_fallback_column_found():
    row = pd.Series({'Other': 'x'})
    with pytest.raises(KeyError):
        utils.resolve_col(row, ['اللقب', 'اللـقـــب'])


# ── build_text ─────────────────────────────────────────────────────────────


def test_build_text_injects_line_count_for_counter_sentinel():
    fields = [('<cardNo>', config.LINE_COUNT_SENTINEL, utils._plain)]
    row = pd.Series({}, dtype=object)

    text = utils.build_text(fields, row, 42)

    assert text == '<cardNo>42<cpf>1<EOR>\r\n'


def test_build_text_applies_processor_and_concatenates_tags():
    fields = [
        ('<arabic>', 'Name', utils._plain),
        ('<national>', 'NID', utils._checked),
    ]
    row = pd.Series({'Name': 'Sara', 'NID': '  9001  '})

    text = utils.build_text(fields, row, 1)

    assert text == '<arabic>Sara<national>9001<cpf>1<EOR>\r\n'


# ── resolve_fields / missing_field_columns ───────────────────────────────────


def test_resolve_fields_maps_processor_keys_to_callables():
    prof = {'fields': [
        {'tag': '<a>', 'column': 'A', 'processor': 'col_check'},
        {'tag': '<b>', 'column': 'B', 'processor': None},
    ]}

    assert utils.resolve_fields(prof) == [('<a>', 'A', utils._checked), ('<b>', 'B', utils._plain)]


def test_missing_field_columns_lists_tags_without_any_matching_column():
    prof = {'fields': [
        {'tag': '<ok>', 'column': 'A', 'processor': None},
        {'tag': '<fallback-ok>', 'column': ['Missing', 'B'], 'processor': None},
        {'tag': '<gone>', 'column': 'Missing', 'processor': None},
        {'tag': '<all-gone>', 'column': ['X', 'Y'], 'processor': None},
        {'tag': '<counter>', 'column': config.LINE_COUNT_SENTINEL, 'processor': None},
        {'tag': '<empty>', 'column': None, 'processor': None},
    ]}

    assert utils.missing_field_columns(prof, ['A', 'B']) == ['<gone>', '<all-gone>']


# ── detect_profile ─────────────────────────────────────────────────────────


def prof(name, signatures, lookup_col='Card No'):
    return {'name': name, 'signatures': signatures, 'lookup_col': lookup_col, 'fields': []}


def test_detect_profile_matches_default_debit_cards_profile():
    profile = utils.detect_profile(['Card No', 'Other Column'], config.DEFAULT_PROFILES)

    assert profile['name'] == 'debit-cards'
    assert profile['lookup_col'] == 'Card No'


@pytest.mark.parametrize('order', [1, -1])
def test_detect_profile_most_specific_match_wins_regardless_of_order(order):
    # Columns satisfy both profiles; the one with more identifying columns
    # must win whichever comes first in the list.
    profiles = [prof('debit-cards', ['Card No']), prof('prepaid', ['Card No', 'Wallet ID'])][::order]

    assert utils.detect_profile(['Card No', 'Wallet ID'], profiles)['name'] == 'prepaid'
    assert utils.detect_profile(['Card No'], profiles)['name'] == 'debit-cards'


def test_detect_profile_raises_on_equally_specific_matches():
    profiles = [prof('a', ['Card No', 'X']), prof('b', ['Card No', 'Y'])]

    with pytest.raises(ProfileDetectionError, match='a, b'):
        utils.detect_profile(['Card No', 'X', 'Y'], profiles)


def test_detect_profile_ignores_profiles_without_signatures():
    profiles = [prof('draft', []), prof('debit-cards', ['Card No'])]

    assert utils.detect_profile(['Card No'], profiles)['name'] == 'debit-cards'


def test_detect_profile_raises_when_no_signature_matches():
    with pytest.raises(ProfileDetectionError, match='debit-cards'):
        utils.detect_profile(['Unrelated Column'], config.DEFAULT_PROFILES)


def test_detect_profile_raises_missing_column_when_lookup_col_absent():
    with pytest.raises(MissingColumnError):
        utils.detect_profile(['Trigger'], [prof('broken', ['Trigger'], lookup_col='Not Present')])


# ── get_source_files ───────────────────────────────────────────────────────


def test_get_source_files_lists_p3_files_excluding_previous_output(tmp_path):
    (tmp_path / 'card1.p3').write_bytes(b'data')
    (tmp_path / 'card2.p3').write_bytes(b'data')
    (tmp_path / 'notes.txt').write_bytes(b'data')
    (tmp_path / 'card1_processed.p3').write_bytes(b'previous run')

    files = utils.get_source_files(tmp_path)

    assert sorted(files) == ['card1.p3', 'card2.p3']


def test_get_source_files_raises_when_none_found(tmp_path):
    with pytest.raises(SourceFilesError):
        utils.get_source_files(tmp_path)


def test_output_path_for_uses_first_source_file_name(tmp_path):
    assert utils.output_path_for(tmp_path, ['cards 01.p3', 'cards 02.p3']) == tmp_path / 'cards 01_processed.p3'


# ── load_excel ─────────────────────────────────────────────────────────────


def test_load_excel_strips_whitespace_and_drops_generated_columns(tmp_path):
    df = pd.DataFrame({' Card No ': ['1001'], 'Name': ['Ali'], 'Column1': ['junk']})
    path = tmp_path / 'sample.xlsx'
    df.to_excel(path, index=False)

    result = utils.load_excel(str(path))

    assert list(result.columns) == ['Card No', 'Name']
    assert result.loc[0, 'Card No'] == '1001'


def test_load_excel_reads_blank_cell_as_nan(tmp_path):
    # Documents real pandas behavior: dtype=str only applies to non-missing values, so a blank
    # Excel cell still comes back as NaN — the exact input the processor NaN-guards above handle.
    df = pd.DataFrame({'Card No': ['1001'], 'Notes': [None]})
    path = tmp_path / 'sample.xlsx'
    df.to_excel(path, index=False)

    result = utils.load_excel(str(path))

    assert pd.isna(result.loc[0, 'Notes'])
