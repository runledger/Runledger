"""Keep external diagnostic text valid in XML 1.0 artifacts."""

from __future__ import annotations

import re

_INVALID_XML_CHARACTERS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def sanitize_xml_text(value: str) -> str:
    """Replace forbidden code points while retaining readable Unicode and whitespace."""
    return _INVALID_XML_CHARACTERS.sub("\ufffd", value)
