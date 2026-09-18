from __future__ import annotations

import re
from typing import Any

import pandas as pd

PAM04_SUBTYPE_RE = re.compile(r"\bPAM04(?:[-_][A-Za-z0-9]+)+\b", re.IGNORECASE)


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "unknown", "na"} else text


def normalize_side(value: Any) -> str:
    text = _text(value).lower()
    if text in {"l", "left"}:
        return "L"
    if text in {"r", "right"}:
        return "R"
    return ""


def pam04_subtype(*values: Any) -> str | None:
    """Extract an explicitly annotated legacy PAM04 subtype label.

    Connectivity is never used to invent a subtype. This only recognises labels
    already present in metadata, e.g. PAM04-can, PAM04-dd or PAM04-nc.
    """
    for value in values:
        text = _text(value)
        if not text:
            continue
        match = PAM04_SUBTYPE_RE.search(text)
        if match:
            label = match.group(0).replace("_", "-")
            return "PAM04" + label[len("PAM04"):].lower()
    return None
