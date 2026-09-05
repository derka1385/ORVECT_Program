import re


NAMESPACE_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{1,79}")
IDENTIFIER_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9._:/ +\-]{0,79}")
UDS_DISPLAY_PATTERN = re.compile(r"([PBCU][0-9A-F]{4})\s+([0-9A-F]{2})(?:\s+\[(\d{1,3})\])?")


def split_uds_display(value: str) -> dict:
    """Parse the documented scanner display syntax, not numeric alias conversions.

    Bracketed decimal status is transient. Six-digit raw identities are retained
    verbatim; their representation cannot be guessed from arithmetic.
    """
    normalized = " ".join((value or "").strip().upper().split())
    match = UDS_DISPLAY_PATTERN.fullmatch(normalized)
    if not match:
        return {"code": normalize_identifier(normalized), "failure_type": None, "status_byte": None}
    status = int(match[3]) if match[3] else None
    if status is not None and status > 255:
        raise ValueError("DTC status byte must be between 0 and 255")
    return {"code": match[1], "failure_type": match[2], "status_byte": status}


def normalize_namespace(value: str) -> str:
    normalized = (value or "").strip().casefold()
    if not NAMESPACE_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid diagnostic namespace")
    return normalized


def normalize_identifier(value: str) -> str:
    normalized = " ".join((value or "").strip().upper().split())
    if not IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid diagnostic identifier")
    return normalized
