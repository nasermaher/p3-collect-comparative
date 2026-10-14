# ── main.py ───────────────────────────────────────────────────────────────────
# P3CC — Card Data Collect-Comparative Tool - Version 3.1
# Processing pipeline + a minimal console entry point for developer debugging.
# Contains no business logic — all logic lives in utils.py and config.py.
# The GUI entry point (app.py / gui.py) imports run_pipeline() directly.
# ──────────────────────────────────────────────────────────────────────────────

import sys
import time
import logging
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from exceptions import P3CCError
from config import ENCODING, CARD_ID_START, CARD_ID_END, END_MARKER
from utils  import (
    select_file,
    get_source_files,
    output_path_for,
    load_excel,
    detect_profile,
    build_text,
    get_resolved_field_map,
    iter_records,
    check_record,
    record_serial,
)
from settings import get_app_dir

# ── Logging setup ─────────────────────────────────────────────────────────────
# Configured here so it's active for the entire process including utils imports.
# Logged next to the app (not cwd) so a double-clicked exe always finds its log.

_log_path = get_app_dir() / 'p3cc.log'
_handlers = [logging.FileHandler(_log_path, encoding='utf-8')]
if sys.stderr is not None:
    # A --windowed PyInstaller build has no console, so sys.stderr is None —
    # adding a StreamHandler in that case would crash on the first log call.
    _handlers.append(logging.StreamHandler())

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=_handlers,
)
log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# ── Processing pipeline ──────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────

def run_pipeline(
    p3_root: Path,
    excel_path: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """
    Run the full P3CC batch: discover source files, load Excel, detect
    profile, and stream each .p3 file, injecting looked-up card data.

    Args:
        p3_root:            Folder containing the .p3 source files.
        excel_path:         Path to the Excel data file.
        progress_callback:  Optional callable(current, total) invoked once
                             per file processed, for UI progress bars.

    Returns:
        dict with keys: file_count, total_card_count, skip_count,
        elapsed, output_path.

    Raises:
        SourceFilesError, ProfileDetectionError, MissingColumnError,
        P3CCError — callers should catch these and present a clean message.
    """
    p3_root = Path(p3_root)

    files = get_source_files(p3_root)
    log.info('Source files  : %d file(s) found', len(files))

    p3_fileout = output_path_for(p3_root, files)
    log.info('Output file   : %s', p3_fileout)

    start_time = time.time()

    excel = load_excel(excel_path)

    profile, lookup_col = detect_profile(excel.columns)
    log.info('Profile active: [%s]  |  Index key: [%s]', profile, lookup_col)

    # O(1) card lookups — index set once here, used inside the loop
    excel.set_index(lookup_col, inplace=True, drop=False)

    # Loaded once per batch (not per card) — reflects any edits made in the
    # GUI's Manage Fields dialog since the last run, without needing a restart.
    resolved_field_map = get_resolved_field_map()

    file_count       = 0
    total_card_count = 0
    skip_count       = 0
    warning_count    = 0
    discard_count    = 0

    log.info('Starting batch: %d file(s) to process', len(files))

    with open(p3_fileout, 'ab+') as file_out:
        file_out.seek(0)
        file_out.truncate()

        for filename in files:

            file_name  = p3_root / filename
            file_count += 1
            line_count  = 0

            prev_serial = None
            discarded   = []   # (line_no, byte length) of lines outside any record

            with open(file_name, 'rb') as file_in:

                # Each record is one whole card block — embedded CR/LF bytes in
                # the encrypted data are kept intact (see utils.iter_records).
                records = iter_records(file_in, on_discard=lambda n, line: discarded.append((n, len(line))))
                for record in records:
                    line_count += 1

                    # ── Validate record layout ────────────────────────────
                    problems = check_record(record, prev_serial)
                    for problem in problems:
                        log.warning('%s, record #%d: %s', filename, line_count, problem)
                    if problems:
                        warning_count += 1
                    prev_serial = record_serial(record)

                    if not record.endswith(END_MARKER):
                        skip_count += 1
                        continue

                    card_id = record[CARD_ID_START:CARD_ID_END].decode(ENCODING)

                    # ── Append card data after END marker ─────────────────
                    try:
                        excel_row = excel.loc[card_id]

                        # Resolve to Series if duplicate card IDs exist in Excel
                        if isinstance(excel_row, pd.DataFrame):
                            excel_row = excel_row.iloc[0]

                        # Build & write
                        text = build_text(profile, excel_row, line_count, resolved_field_map)

                        # ── Write the record untouched, then the tags right after #END# ──
                        file_out.write(record)
                        file_out.write(text.encode(ENCODING, errors='replace'))

                    except KeyError as e:
                        # Catches missing card_id in Excel.loc or missing column in build_text (via resolve_col)
                        log.warning('Data lookup error for card %s: %s — skipping.', card_id, e)
                        skip_count += 1

            # Content is deliberately not logged — it may be confidential card data.
            for line_no, size in discarded:
                log.warning('%s, line %d: discarded %d byte(s) outside any card record', filename, line_no, size)
            discard_count    += len(discarded)
            total_card_count += line_count

            if progress_callback is not None:
                progress_callback(file_count, len(files))

    elapsed = time.time() - start_time
    log.info('─' * 55)
    log.info('Files processed : %d', file_count)
    log.info('Cards read : %d, Cards written : %d, Cards skipped : %d', total_card_count, total_card_count - skip_count, skip_count)
    log.info('Records with layout warnings : %d', warning_count)
    log.info('Lines discarded outside records : %d', discard_count)
    log.info('Elapsed time    : %.4f seconds', elapsed)
    log.info('─' * 55)

    return {
        'file_count': file_count,
        'total_card_count': total_card_count,
        'skip_count': skip_count,
        'warning_count': warning_count,
        'discard_count': discard_count,
        'elapsed': elapsed,
        'output_path': p3_fileout,
    }


# ──────────────────────────────────────────────────────────────────────────
# ── Console entry point (developer debugging only) ─────────────────────────
# ──────────────────────────────────────────────────────────────────────────

def main() -> None:

    print('\n.. P3CC (Collect-Comparative) Started ..\n')

    p3_file_name = select_file(title='Select any file inside the P3 folder')
    if not p3_file_name:
        sys.exit('\nAborted: No processing file selected.')
    p3_root = Path(p3_file_name).parent

    excel_path = select_file(title='Select the Excel data file')
    if not excel_path:
        sys.exit('\nAborted: No Excel data file selected.')

    try:
        result = run_pipeline(p3_root, excel_path)
    except P3CCError as e:
        log.error(str(e))
        sys.exit(f'[ERROR] {e}')
    except Exception:
        log.exception('Unexpected error occurred during card data processing.')
        sys.exit(1)

    print(f"\nDone — output written to: {result['output_path']}")


if __name__ == '__main__':
    main()
