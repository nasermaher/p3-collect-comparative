# ── config.py ─────────────────────────────────────────────────────────────────
# All constants and field definitions for P3CC.  - Version 3.2
# Edit this file to: change encoding, markers, or the built-in default profiles.
# No logic lives here — only data.
# ──────────────────────────────────────────────────────────────────────────────

VERSION = "3.2"
# ── File & encoding constants ─────────────────────────────────────────────────

ENCODING      = 'cp1256'
CARD_FILE_EXT = 'p3'

# Output file = first source file's name + this suffix (cards.p3 → cards_processed.p3).
# Source files ending with it are skipped, so a previous run's output is never re-read.
OUTPUT_SUFFIX = '_processed'

# ── Binary markers (used when scanning .p3 source files) ─────────────────────

CARD_MARKER: bytes = b'"%B'
END_MARKER: bytes  = b'#END#'

# ── Card record layout ────────────────────────────────────────────────────────
# Every record starts with a fixed header and ends with END_MARKER:
#   <8-digit serial>"%B<16-digit card ID><encrypted data, may contain CR/LF>#END#
# The encrypted data is copied byte-for-byte and never altered.

SERIAL_LEN    = 8
CARD_ID_START = 11   # SERIAL_LEN + len(CARD_MARKER)
CARD_ID_END   = 27   # 16-digit card ID

# ── Card-counter sentinel ─────────────────────────────────────────────────────
# A field whose column is this sentinel gets the running card counter, not an
# Excel value.

LINE_COUNT_SENTINEL = '__line_count__'

# ── Default profiles (seed / reset data) ──────────────────────────────────────
# Profiles themselves are user-editable: they live in field_map.json next to
# the exe and are managed from the GUI's "Manage Profiles" dialog. This list
# is only what a fresh install starts from and what "Reset All to Defaults"
# restores. Each profile is:
#
#   name        → str        : unique profile name, e.g. 'debit-cards'
#   signatures  → list[str]  : identifying Excel columns — ALL must be present
#                              for the profile to be detected. When several
#                              profiles match, the one with the most matching
#                              identifying columns wins (see detect_profile()).
#   lookup_col  → str        : the card-ID column the Excel sheet is indexed on
#   fields      → list[dict] : {'tag', 'column', 'processor'} — the tags injected
#                              after #END#, in order:
#       column    → str            : Excel column name
#                   list[str]      : fallback list — first found column is used
#                   None           : tag written with an empty value
#                   LINE_COUNT_SENTINEL : injects the running card counter
#       processor → str | None     : key into utils._PROCESSOR_REGISTRY
#                                    ('col_check', 'chr_replace', 'jpg'),
#                                    None = plain str()

DEFAULT_PROFILES = [
    {
        'name': 'debit-cards',
        'signatures': ['Card No'],
        'lookup_col': 'Card No',
        'fields': [
            {'tag': '<arabic>',       'column': 'CardHolder Name',   'processor': None},
            {'tag': '<national>',     'column': 'NID',               'processor': 'col_check'},
            {'tag': '<postoffice>',   'column': 'Post Office Name2', 'processor': None},
            {'tag': '<region>',       'column': 'Post Region',       'processor': 'col_check'},
            {'tag': '<barcode>',      'column': 'Barcode',           'processor': None},
            {'tag': '<IssuanceDate>', 'column': 'Issue Date',        'processor': None},
        ],
    },
]

# ── Migration of field_map.json files from versions before 3.2 ────────────────
# Old files only held {profile_name: [fields]}; profile detection was hardcoded.
# On migration, a renamed profile keeps its fields and takes its identifying
# columns from the DEFAULT_PROFILES entry of its new name. Retired profiles are
# dropped (still kept in the backup copy). Any other profile name is kept with
# no identifying columns, so it's never auto-detected until the user sets them.

LEGACY_PROFILE_RENAMES = {'classic': 'debit-cards'}
RETIRED_PROFILES       = ('yalla', 'zamalek')


# ── Arabic character normalization ────────────────────────────────────────────
# Translation table built once at module load — applied via C-level translate().
#   • Eastern Arabic-Indic digits (U+0660–U+0669) → ASCII '0'–'9'
#   • ڤ Veh (U+06A4 = 1700) → '_'
#   • PDF — Pop Directional Formatting (U+202C = 8236) → '_'
#   • Any codepoint > 65381 → '_'  (handled in chr_replace pre-pass)

NORMALIZATION_TABLE = {
    1632: '0', 1633: '1', 1634: '2', 1635: '3', 1636: '4',
    1637: '5', 1638: '6', 1639: '7', 1640: '8', 1641: '9',
    1700: '_', 8236: '_',
}
