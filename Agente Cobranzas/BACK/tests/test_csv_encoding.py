"""Encoding contract for the official cp1252 exports consumed by Collections."""

from __future__ import annotations

import pytest

from collections_agent.data import _decode_csv
from collections_agent.uploads import CsvValidationError, _decode

CP1252_ONLY = "GRUPO—001"


def test_dataset_rows_keep_cp1252_only_glyphs() -> None:
    """A latin1 fallback would decode 0x97 as a C1 control instead of an em dash."""
    content = f"RAZON_SOCIAL|COD_CUENTA\n{CP1252_ONLY}|ACC_001\n".encode("cp1252")

    rows = _decode_csv(content)

    assert rows[0]["RAZON_SOCIAL"] == CP1252_ONLY


def test_uploads_keep_cp1252_only_glyphs() -> None:
    assert _decode(CP1252_ONLY.encode("cp1252")) == CP1252_ONLY


def test_uploads_reject_undecodable_bytes() -> None:
    """Fail loudly instead of storing silent mojibake."""
    with pytest.raises(CsvValidationError):
        _decode(b"RAZON_SOCIAL\nA\x81B\n")
