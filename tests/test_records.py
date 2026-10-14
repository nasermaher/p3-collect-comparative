import pandas as pd

import field_map_store
import main
import utils

# Synthetic records only — fake card IDs and fake "encrypted" payloads.
# Payloads deliberately contain bare CR, bare LF and CRLF bytes, which are
# part of the card data and must survive byte-for-byte.

PAYLOAD_1 = b'AB\r\nCD\nEF\rGH'
PAYLOAD_2 = b'plain-payload'


def make_record(serial: int, card_id: str, payload: bytes) -> bytes:
    return b'%08d"%%B%s%s#END#' % (serial, card_id.encode(), payload)


REC_1 = make_record(1, '1111222233334444', PAYLOAD_1)
REC_2 = make_record(2, '5555666677778888', PAYLOAD_2)


def records_of(data: bytes, discarded: list | None = None) -> list[bytes]:
    # Same line-splitting as iterating a file opened 'rb' (LF only)
    lines = [l + b'\n' for l in data.split(b'\n')]
    lines[-1] = lines[-1][:-1]
    if not lines[-1]:
        lines.pop()
    on_discard = (lambda n, line: discarded.append((n, line))) if discarded is not None else None
    return list(utils.iter_records(lines, on_discard=on_discard))


# ── iter_records ────────────────────────────────────────────────────────────


def test_iter_records_keeps_embedded_cr_lf_inside_one_record():
    assert records_of(REC_1 + b'\r\n' + REC_2 + b'\r\n') == [REC_1, REC_2]


def test_iter_records_handles_last_record_without_trailing_newline():
    assert records_of(REC_1 + b'\r\n' + REC_2) == [REC_1, REC_2]


def test_iter_records_drops_and_reports_lines_outside_records():
    discarded = []
    data = b'HEADER\r\n' + REC_1 + b'\r\n\r\njunk\r\n' + REC_2 + b'\r\nFOOTER'
    assert records_of(data, discarded) == [REC_1, REC_2]
    # REC_1 spans physical lines 2-4 (its payload has two LFs), REC_2 is line 7
    assert discarded == [(1, b'HEADER\r\n'), (5, b'\r\n'), (6, b'junk\r\n'), (8, b'FOOTER')]


def test_iter_records_stray_line_is_not_glued_to_first_record():
    assert records_of(b'stray\r\n' + REC_1 + b'\r\n') == [REC_1]


def test_iter_records_yields_incomplete_trailing_record_unchanged():
    partial = b'00000003"%B9999000099990000' + PAYLOAD_1
    assert records_of(REC_1 + b'\r\n' + partial) == [REC_1, partial]


# ── check_record ────────────────────────────────────────────────────────────


def test_check_record_accepts_well_formed_sequence():
    assert utils.check_record(REC_1, None) == []
    assert utils.check_record(REC_2, 1) == []


def test_check_record_flags_malformed_header():
    bad = b'0000001X"%B1111222233334444data#END#'
    assert any('malformed header' in p for p in utils.check_record(bad, None))


def test_check_record_flags_serial_gap():
    assert any('does not follow' in p for p in utils.check_record(REC_2, 5))


def test_check_record_flags_missing_end_marker():
    assert any('incomplete' in p for p in utils.check_record(REC_1[:-5], None))


def test_check_record_flags_merged_records():
    merged = REC_1[:-5] + b'\r\n' + REC_2   # first record lost its #END#
    problems = utils.check_record(merged, None)
    assert any('another record header' in p for p in problems)


# ── run_pipeline end-to-end (synthetic data) ─────────────────────────────────


def test_run_pipeline_writes_records_untouched_with_tags_after_end(tmp_path, app_dir, monkeypatch):
    src = tmp_path / 'batch'
    src.mkdir()
    (src / 'cards.p3').write_bytes(REC_1 + b'\r\n' + REC_2 + b'\r\n')

    field_map_store.save_profiles([{
        'name': 'debit-cards', 'signatures': ['Card No'], 'lookup_col': 'Card No',
        'fields': [{'tag': '<name>', 'column': 'Name', 'processor': None}],
    }])
    excel = pd.DataFrame({'Card No': ['1111222233334444', '5555666677778888'], 'Name': ['A', 'B']})
    monkeypatch.setattr(main, 'load_excel', lambda path: excel)

    result = main.run_pipeline(src, 'unused.xlsx')

    out = result['output_path'].read_bytes()
    assert out == REC_1 + b'<name>A<cpf>1<EOR>\r\n' + REC_2 + b'<name>B<cpf>1<EOR>\r\n'
    assert result['profile'] == 'debit-cards'
    assert result['field_map_notice'] is None
    assert result['skip_count'] == 0
    assert result['warning_count'] == 0
