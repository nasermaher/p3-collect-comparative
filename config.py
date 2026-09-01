# ── config.py ─────────────────────────────────────────────────────────────────
# All constants and field definitions for P3CC.  - Version 3.0
# Edit this file to: change encoding, add profiles, or modify field mappings.
# No logic lives here — only data.
# ──────────────────────────────────────────────────────────────────────────────

VERSION = "3.0"
# ── File & encoding constants ─────────────────────────────────────────────────

ENCODING      = 'cp1256'
CARD_FILE_EXT = 'p3'

# ── Binary markers (used when scanning .p3 source files) ─────────────────────

CARD_MARKER: bytes = b'"%B'
END_MARKER: bytes  = b'#END#'

# ── Card ID byte slice offsets inside a CARD_MARKER line ─────────────────────

CARD_ID_START = 11
CARD_ID_END   = 27

# ── Profile signatures ────────────────────────────────────────────────────────
# Maps profile name → dictionary containing:
#   'signatures': list of column names that MUST exist in the Excel file
#                 for that profile to be selected.
#   'lookup_col': the column name to use for indexing the Excel DataFrame.
# Order matters: first match wins in detect_profile().

PROFILE_SIGNATURES = {
    'yalla': {
        'signatures': ['Card No', 'Mobile Number'],
        'lookup_col': 'Card No',  # Assuming 'Card No' is the lookup for yalla profile
    },
    'classic': {
        'signatures': ['Card No'],
        'lookup_col': 'Card No',
    },
    'zamalek': {
        'signatures': ['رقم بطاقة الصراف الالى'],
        'lookup_col': 'رقم بطاقة الصراف الالى',
    },
}

# ── Field map ─────────────────────────────────────────────────────────────────
# Each entry is a tuple: (output_tag, col_def, processor_key)
#
#   output_tag    → str            : the tag written to the output file
#   col_def       → str            : fixed Excel column name
#                   list[str]      : fallback list — first found column is used
#                   None           : no column value; tag written with empty value
#                   "__line_count__": special sentinel — injects the card counter
#   processor_key → str | None     : key for _PROCESSOR_REGISTRY in utils.py
#                                    None is replaced with _plain at startup
#                                    by _normalize_field_map() in utils.py
#
# To add a new profile: add its signature to PROFILE_SIGNATURES above,
# then add its field list here. No other file needs to change.
# ──────────────────────────────────────────────────────────────────────────────

FIELD_MAP = {
    'yalla': [
        ('<arabic>', 'CardHolder Name', None),
        ('<national>', 'NID', 'col_check'),
        ('<postoffice>', 'Post Office Name2', 'chr_replace'),
        ('<region>', 'Post Region', 'col_check'),
        ('<barcode>', 'Barcode', None),
        ('<ClientNo>', 'Client No', None),
        ('<MobileNumber>', 'Mobile Number', None),
        ('<IssuanceDate>', 'Issue Date', None),
        ('<address>', 'Address', None),
        ('<city>', 'City', None),
    ],
    'classic': [
        ('<arabic>',        'CardHolder Name',      None),
        ('<national>',      'NID',                  'col_check'),
        ('<postoffice>',    'Post Office Name2',    None),
        ('<region>',        'Post Region',          'col_check'),
        ('<barcode>',       'Barcode',              None),
        ('<IssuanceDate>',  'Issue Date',           None),
    ],
    'zamalek': [
        ('<cardNo>',                  '__line_count__',             None),  # injected counter
        ('<fullname>',                ['الاسم', 'الإســــــم'],       None),
        ('<title>',                   ['اللقب', 'اللـقـــب'],       'col_check'),
        ('<desc>',                    'الصفة',                      'col_check'),
        ('<membershipNo>',            'رقم العضوية',                None),
        ('<paymentDate><paymentNo>',  None,                         None),  # hardcoded empty tag pair
        ('<Image>',                   'الصورة',                     'jpg'),
        ('<VisaCardNo>',              'رقم بطاقة الصراف الالى',      None),
        ('<IssuanceDate>',            'تاريخ الاصدار',               None),
        ('<address>',                 None,                         None),  # empty tag
    ],
}


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
