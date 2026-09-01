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
    field_map = {'zamalek': [('<cardNo>', '__line_count__', utils._plain)]}
    row = pd.Series({}, dtype=object)

    text = utils.build_text('zamalek', row, 42, field_map)

    assert text == '<cardNo>42<cpf>1<EOR>\r\n'


def test_build_text_applies_processor_and_concatenates_tags():
    field_map = {
        'classic': [
            ('<arabic>', 'Name', utils._plain),
            ('<national>', 'NID', utils._checked),
        ]
    }
    row = pd.Series({'Name': 'Sara', 'NID': '  9001  '})

    text = utils.build_text('classic', row, 1, field_map)

    assert text == '<arabic>Sara<national>9001<cpf>1<EOR>\r\n'


# ── detect_profile ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('columns', 'expected_profile'),
    [
        (['Card No', 'Mobile Number'], 'yalla'),
        (['Card No', 'Other Column'], 'classic'),
        (['رقم بطاقة الصراف الالى'], 'zamalek'),
    ],
)
def test_detect_profile_matches_real_signatures(columns, expected_profile):
    profile, lookup_col = utils.detect_profile(columns)

    assert profile == expected_profile
    assert lookup_col == config.PROFILE_SIGNATURES[expected_profile]['lookup_col']


def test_detect_profile_first_match_wins_when_multiple_signatures_satisfied():
    # yalla is declared before classic in PROFILE_SIGNATURES, and columns containing both
    # 'Card No' and 'Mobile Number' satisfy both signatures — yalla must win, not classic.
    profile, _ = utils.detect_profile(['Card No', 'Mobile Number'])
    assert profile == 'yalla'


def test_detect_profile_raises_when_no_signature_matches():
    with pytest.raises(ProfileDetectionError):
        utils.detect_profile(['Unrelated Column'])


def test_detect_profile_raises_missing_column_when_lookup_col_absent(monkeypatch):
    monkeypatch.setitem(
        utils.PROFILE_SIGNATURES,
        'broken',
        {'signatures': ['Trigger'], 'lookup_col': 'Not Present'},
    )

    with pytest.raises(MissingColumnError):
        utils.detect_profile(['Trigger'])


# ── get_source_files ───────────────────────────────────────────────────────


def test_get_source_files_lists_p3_files_excluding_output(tmp_path):
    (tmp_path / 'card1.p3').write_bytes(b'data')
    (tmp_path / 'card2.p3').write_bytes(b'data')
    (tmp_path / 'notes.txt').write_bytes(b'data')
    output_file = tmp_path / 'output.p3'
    output_file.write_bytes(b'previous run')

    files = utils.get_source_files(tmp_path, output_file)

    assert sorted(files) == ['card1.p3', 'card2.p3']


def test_get_source_files_raises_when_none_found(tmp_path):
    with pytest.raises(SourceFilesError):
        utils.get_source_files(tmp_path, tmp_path / 'output.p3')


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
