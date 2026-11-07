"""Stands in for the GPL `unidecode` package, which edgartools imports for matching company names in its search.

FinHub only depends on Apache, MIT and BSD code, so pyproject.toml keeps the real one out. This uses the standard
library: accents and similar marks are removed, and anything else outside ASCII is dropped.
"""

from __future__ import annotations

import unicodedata


def unidecode(text: str, errors: str = "ignore", replace_str: str = "") -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
