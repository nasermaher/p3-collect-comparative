# P3CC — Project History & Decisions

This is the record of what was built, why, and the constraints behind it, so a future session can pick up advanced work without repeating old discussions. `CLAUDE.md` describes how the code works. This file describes **why it is the way it is**. Newest entries are first within each section.

---

## Working agreements (how the owner works)

- The owner communicates in **Arabic**. Reply in Arabic. Code, comments, commit messages and GUI text stay in English, and both READMEs are kept in sync (`README.md` + `README-ar.md`).
- **Real card data is confidential.** Never ask for real `.p3` or Excel files, and never put real data into tests, logs or docs. Use synthetic records (fake card IDs like `1111222233334444`). To diagnose a problem, ask for specific `p3cc.log` lines, which contain no encrypted payloads.
- **Test before commit.** Implement, run `pytest`, rebuild the package, then wait for the owner to test on real files (and sometimes the client too) before committing. Commit when the owner confirms.
- **Every release:** bump `config.VERSION`, add a "What's new in X.Y" section to both READMEs, then run `toolkit.bat package`. That runs the tests, builds the exe and creates `P3CC-vX.Y-portable.zip`. The READMEs are bundled into the exe (in-app Help), so rebuild after any README change.
- The packaged zip goes to the client: the whole `dist/P3CC` folder, never the `.exe` alone.
- **GitHub Release per version:** after the owner confirms and the commits are pushed, rebuild the zip from that exact HEAD. Then create release `vX.Y` on that commit with the zip attached and bilingual notes (English plus an Arabic summary, including upgrade steps). `gh` isn't installed, so this goes through the GitHub REST API using the token from `git credential fill`, which is piped in and never printed. Afterwards, check that the downloaded asset's SHA-256 matches the local zip. If a tag is later moved to a newer commit, re-point the release (`target_commitish`) and replace the asset with a zip rebuilt from that commit, because the bundled READMEs may differ. Released so far: **v3.2** (2026-10-14; the tag sits on the latest commit of that day, the one that records this sentence; asset SHA-256 `41521573…`, built from `89675da`, whose code and READMEs are identical).
- **After packaging, the owner often moves the built zip into `_archive/`.** If `P3CC-vX.Y-portable.zip` is missing from the repo root, look there before rebuilding.

## Repository & infrastructure

- **GitHub:** https://github.com/nasermaher/p3-collect-comparative. The repo is **public**, so nothing confidential may ever be committed. The branch is `main` (the local branch was renamed from `master` on 2026-10-14), and local `main` tracks `origin/main`, so a plain `git push` works. The repo description and topics (python, tkinter, pyinstaller, excel, windows-desktop, card-issuance) are set. Both READMEs open with an English | العربية language switcher and include `git clone` instructions.
- **CI:** GitHub Actions `.github/workflows/python-app.yml`, added by the owner from the GitHub website. It runs on push/PR to `main` with Python 3.10: flake8 syntax/undefined-name check, then `pytest`. The owner may add commits on GitHub directly (the workflow itself, and the deletion of `error.jpg`, were made on the website), so **fetch before pushing**. If a push is rejected, inspect the remote commit and rebase onto it. Never force-push over it.
- **`_archive/`** is the owner's private folder (old zips, chat logs). It's gitignored, and it was purged from history with a rewrite and force-push (2026-10-14). Never commit or package it.
- **Repo contents are project files only.** On 2026-10-14 the scratch and working files `test.py`, `handoff.txt` (an old session handoff), `gemini-audit.md` (an external audit transcript) and `P3cc_prd.md` (the original GUI/portability plan, now implemented) were moved out of the repo into `_archive/`. Keep notes, transcripts and experiments there, not in the repo.
- **Gitignored runtime files:** `settings.json`, `field_map.json`, `field_map.*.json` (backups), `field_map.tmp`, `p3cc.log`, `P3CC-v*-portable.zip`, `build/`, `dist/`.

## Session log

### 2026-10-14
A full working session. Everything below is committed and pushed, and CI is green.
1. **3.1:** whole-record `.p3` processing (embedded CR/LF preserved byte-for-byte), record layout checks, logged removal of lines outside records, and the output named `<first source>_processed.p3`.
2. **3.2:** user-managed profiles in `field_map.json` v2, the Manage Profiles dialog, `debit-cards` as the only default, most-specific detection, automatic migration of old files and Import…, visible `field_map.json` errors, Test with Excel File, and tag validation.
3. **Docs:** both READMEs gained "What's new" for 3.1 and 3.2 and "Rules for editing profiles" (what reaches the card machines). This file was created and is imported by `CLAUDE.md`.
4. **GitHub:** the repo was published, with its description, topics and README language links. `_archive/` was ignored and purged from history (force-push, so all commit IDs changed). The local branch was renamed to `main`. The owner added CI and deleted `error.jpg` from the website. The non-project files were moved to `_archive/`.
5. **Release v3.2** was published with the portable zip. The tag was then moved to the cleaned-up commit `89675da`, with the asset rebuilt and replaced, and finally to the commit that adds this session log. That last move only changed `PROJECT_HISTORY.md`, which is not bundled in the exe, so the asset was kept.
6. **Delivered to the client:** the 3.1 and 3.2 portable zips. The owner and client tested 3.1, and the owner tested 3.2, on real files. Open question still pending from the client: whether a **32-bit** build is needed (see Ideas below).

## Release history

### 3.2 (2026-10-14): user-managed card profiles
**Problem reported by the client:** profiles `yalla`/`zamalek` were obsolete, and only `classic` (all debit cards) was still used. Profiles were hardcoded in `config.PROFILE_SIGNATURES`, so they couldn't be added, renamed or removed. A hand-edited `field_map.json` copied from the old version "wasn't read". Likely causes:
1. `yalla` won detection whenever the Excel sheet had `Mobile Number` (first match won), so `classic` edits were never used.
2. The old loader silently fell back to defaults on any read error (bad JSON, UTF-8 BOM, ANSI encoding).

**Decisions:**
- Profiles became user data in `field_map.json` v2: `{"version": 2, "profiles": [{name, signatures, lookup_col, fields}]}`. They're edited in the **Manage Profiles** dialog, which replaced Manage Fields.
- The default and only profile is **`debit-cards`**, identified by `Card No`, card-ID column `Card No`, with the old `classic` fields. Any future distinguishing marker for a new card type is defined as an extra identifying column.
- Detection: **the most specific match wins** (most identifying columns). An equal tie raises `ProfileDetectionError` instead of guessing.
- Migration of pre-3.2 files: `classic` becomes `debit-cards` (fields kept), `yalla`/`zamalek` are dropped, unknown names are kept with no identifying columns. The original is backed up as `field_map.pre-3.2-backup-<ts>.json`. The notice shows **once**, because the file is then saved as v2. **Import…** does the same for a file picked by hand.
- `field_map.json` errors raise `FieldMapError`, are shown at startup and on Run, and the file is **never silently overwritten**. A UTF-8 BOM is accepted. Saves are validated and atomic.
- Tags are validated: `(<[^<>\s]+>)+`, without `<cpf>`/`<EOR>` (P3CC appends `<cpf>1<EOR>\r\n` itself).
- "Test with Excel File" shows the selected profile and any field columns the sheet is missing.
- README section **"Rules for editing profiles"**: the card machines read the output, so tags, order and values must match the machine's settings exactly. Profile names and identifying columns never reach the output. It also documents the Excel pitfalls below, and that every PC has its own `field_map.json`, which must be kept identical.
- Caveat told to the owner: if the client's real edits were in `yalla` (because yalla was being detected), they're only in the pre-3.2 backup and must be re-added to `debit-cards` by hand.

### 3.1 (2026-10-14): record integrity
**Problem:** a `.p3` card record is one *logical* line, `<8-digit serial>"%B<16-digit card ID><encrypted data>#END#`. The encrypted data can contain CR, LF or CRLF bytes. The old loop iterated physical lines and wrote only the line holding `#END#`, so everything before an embedded line break was silently lost.

**Decisions** (confirmed by the owner):
- Serials start at `00000001` in each file and go up by 1, but the start isn't enforced. Only gaps within a file are warned about.
- The card ID is always 16 digits. There are no header/footer lines. Anything outside a record is **dropped and logged per line** (line number + byte count, never content).
- `utils.iter_records()` re-joins lines byte-for-byte. Only the single line terminator after `#END#` is removed, and the Excel tags are appended directly after `#END#` as a continuation of the same line.
- `check_record()` warnings (malformed header, serial gap, missing `#END#`, merged records) are logged. Records with warnings are still written unchanged. Only incomplete records are skipped.
- **Output naming:** the first source file's name + `_processed` (`cards_01.p3` produces `cards_01_processed.p3`). All files are still merged into one output. `*_processed.p3` is never read as input. Old 3.0 outputs (named after the folder) must be deleted from source folders by hand, or they'd be re-read.
- The results panel gained "Layout warnings" and "Lines discarded". Both should be 0 on a clean batch.

### 3.0 and earlier
GUI app (Tkinter) packaged with PyInstaller. Profiles were `yalla` / `classic` / `zamalek`, hardcoded. Output was named after the folder.

## Known pitfalls (worth remembering for new features)

- **Excel 16-digit card numbers** must be stored as Text. Excel keeps 15 significant digits, so the last digit is lost and the card can't be matched.
- `utils.load_excel()` drops columns whose names start with `Col` or `Unn` (pandas auto-names for blank columns). A real column like `Color` would vanish.
- Output encoding is `cp1256` with `errors='replace'`: characters it can't represent become `?`.
- A `--windowed` build has `sys.stderr is None` (handled in `main.py` logging).
- Patching files from Git Bash heredocs on this machine has mangled `\r\n` and `\\s` escapes. Prefer writing helper scripts with the Write tool, and check for stray CR bytes after edits.

## Ideas not yet done (candidates for future work)

- **32-bit Windows build (open question).** The packaged exe is 64-bit only. The owner was checking with the client whether any target machine is 32-bit. If one is, it needs a separate 32-bit Python/venv toolchain, and probably pinned pandas/numpy versions, since recent releases are dropping win32 wheels.

- Per-file output (one `_processed.p3` per source file) instead of one merged file. This was considered when output naming was changed, and the owner chose the merged file.
- Showing per-record warnings in the GUI (currently only counts, with details in `p3cc.log`).
- Checking tag names against a list of tags known to the card machines, if the owner can provide one.
- Enforcing `00000001` as the first serial per file, which the owner explicitly chose *not* to enforce for now.
