# ── exceptions.py ───────────────────────────────────────────────────────────────────

class P3CCError(Exception):
    """Base exception for all P3CC errors."""
    pass


class ProfileDetectionError(P3CCError):
    """Raised when Excel profile cannot be identified."""
    pass


class SourceFilesError(P3CCError):
    """Raised when no source .p3 files are found."""
    pass


class MissingColumnError(P3CCError):
    """Raised when required Excel columns are missing."""
    pass


class InvalidCardError(P3CCError):
    """Raised when card data is malformed."""
    pass