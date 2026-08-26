"""Encoding contract for the official Movistar CSV exports."""

from __future__ import annotations

import pytest

from sonia.persistence.sqlite import CSV_ENCODINGS, count_csv_rows, decode_csv_text


def test_latin1_never_shadows_cp1252() -> None:
    """A permissive fallback would decode every byte and hide the real encoding."""
    assert "latin1" not in CSV_ENCODINGS
    assert "iso-8859-1" not in CSV_ENCODINGS


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"\x93", "“"),
        (b"\x94", "”"),
        (b"\x97", "—"),
        (b"\x80", "€"),
    ],
)
def test_cp1252_only_bytes_keep_their_glyph(raw: bytes, expected: str) -> None:
    """Bytes 0x80-0x9F differ between cp1252 and latin1 and must not become C1 controls."""
    decoded = decode_csv_text(raw)

    assert decoded == expected
    assert not any(0x80 <= ord(character) <= 0x9F for character in decoded)


def test_accented_sources_decode_as_written() -> None:
    """The SUNAT_PROVINCIA export that first broke publication stays readable."""
    assert decode_csv_text("Jaén".encode("cp1252")) == "Jaén"
    assert decode_csv_text("Jaén".encode()) == "Jaén"
    assert decode_csv_text("Jaén".encode("utf-8-sig")) == "Jaén"


def test_undecodable_bytes_fail_loudly() -> None:
    """Publication must reject unknown encodings instead of storing silent mojibake."""
    with pytest.raises(ValueError, match="decodificar"):
        decode_csv_text(b"RAZON_SOCIAL\nA\x81B\n")


def test_row_count_excludes_the_header() -> None:
    content = "COL_A|COL_B\n“X”|1\nY|2\n".encode("cp1252")

    assert count_csv_rows(content) == 2
