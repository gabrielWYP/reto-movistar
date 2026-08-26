"""Encoding contract for the official cp1252 exports consumed by BI."""

from __future__ import annotations

from bi_agent.data import _decode_csv

CP1252_ONLY = "GRUPO—001"


def test_cp1252_only_bytes_keep_their_glyph() -> None:
    """A latin1 fallback would decode 0x97 as a C1 control instead of an em dash."""
    content = f"RAZON_SOCIAL|COD_CUENTA\n{CP1252_ONLY}|ACC_001\n".encode("cp1252")

    rows = _decode_csv(content)

    assert rows[0]["RAZON_SOCIAL"] == CP1252_ONLY
