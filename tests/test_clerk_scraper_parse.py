"""Clerk scraper offline parse tests (validation-plan 1.1 / 1.4).

``clerk_scraper.py`` is ~34 KB of Playwright-driven scraping and is the most
brittle, highest-risk production code. Its *pure* decision functions — those
that turn raw search-result rows / legal descriptions into a "which deed /
plat page is this parcel's" answer — need no browser and can be pinned here:

  - ``_subdiv_name``  tokenize a legal/subdivision into match tokens
  - ``_pick_deed``    pick the subject parcel's vesting deed from a party-search
  - ``_pick_plat_page`` resolve a plat page from a book-only plat search
  - ``_save_pdf``     combine captured page images into a PDF

These cover the exact failure modes the docs describe (wrong-property deed,
deed-vs-plat confusion, unit-number disambiguation) without driving a browser.
"""
from __future__ import annotations

import struct

from app.services import clerk_scraper as cs

# ------------------------------------------------------------------ _subdiv_name


def test_subdiv_name_tokenizes_and_strips_stop_words():
    toks = cs._subdiv_name("IDLEWILD UNIT NO 2 PB 12 PG 5")
    # PB/PG/UNIT/NO/SUB are stop words; numbers dropped; keep subdivision name only
    assert toks == ["IDLEWILD"]


def test_subdiv_name_keeps_multi_word_subdivision():
    toks = cs._subdiv_name("Lake Wales Heights Unit 4")
    assert toks == ["LAKE", "WALES"]


def test_subdiv_name_empty_for_garbage():
    assert cs._subdiv_name("") == []
    assert cs._subdiv_name(None) == []


# ------------------------------------------------------------------ _pick_deed


def _row(doc_type, legal, rec_date="2020-01-01", party_code="R", book="1", page="10"):
    return {
        "doc_type": doc_type, "legal_1": legal, "rec_date": rec_date,
        "party_code": party_code, "book": book, "page": page,
    }


def test_pick_deed_returns_vesting_grantee_deed():
    rows = [
        _row("WD", "IDLEWILD UNIT NO 2", rec_date="2015-05-05"),       # grantor (D)
        _row("WD", "IDLEWILD UNIT NO 2", rec_date="2020-01-01"),       # vesting grantee (R)
        _row("MTG", "IDLEWILD UNIT NO 2", rec_date="2020-02-02"),      # mortgage, not a deed
    ]
    # party_code R = grantee (vesting deed). The WRONG date should win on grantee.
    rows[0]["party_code"] = "D"
    picked = cs._pick_deed(rows, "IDLEWILD")
    assert picked["rec_date"] == "2020-01-01"


def test_pick_deed_ignores_non_deed_doc_types():
    rows = [
        _row("MTG", "IDLEWILD"),
        _row("TAX DEED", "IDLEWILD"),
    ]
    # Only WD/DEED/etc. count; a bare mortgage row must not be picked.
    assert cs._pick_deed(rows, "IDLEWILD") is None


def test_pick_deed_respects_unit_number():
    # Same subdivision name, different unit — must NOT cross-match.
    rows = [_row("WD", "IDLEWILD UNIT 3"), _row("WD", "IDLEWILD UNIT NO 2")]
    picked = cs._pick_deed(rows, "IDLEWILD UNIT NO 2")
    assert "UNIT 3" not in picked["legal_1"]
    assert "UNIT NO 2" in picked["legal_1"]


def test_pick_deed_returns_none_when_no_subdivision_match():
    # Nothing matches the subdivision — return None (keep deep-link), never guess.
    rows = [_row("WD", "LAKESIDE UNIT 1"), _row("WD", "SOME OTHER PLACE")]
    assert cs._pick_deed(rows, "IDLEWILD") is None


def test_pick_deed_picks_most_recent_matching():
    rows = [
        _row("WD", "IDLEWILD", rec_date="1999-01-01"),
        _row("WD", "IDLEWILD", rec_date="2010-06-15"),
        _row("WD", "IDLEWILD", rec_date="2005-03-03"),
    ]
    picked = cs._pick_deed(rows, "IDLEWILD")
    assert picked["rec_date"] == "2010-06-15"


def test_pick_deed_no_deed_rows_returns_none():
    assert cs._pick_deed([], "IDLEWILD") is None
    assert cs._pick_deed([_row("MTG", "IDLEWILD")], "IDLEWILD") is None


# ------------------------------------------------------------------ _pick_plat_page


def test_pick_plat_page_matches_subdivision_and_unit():
    rows = [
        {"legal_1": "IDLEWILD UNIT 3", "page": "31"},
        {"legal_1": "IDLEWILD UNIT NO 2", "page": "17"},
    ]
    assert cs._pick_plat_page(rows, "IDLEWILD UNIT NO 2") == "17"


def test_pick_plat_page_returns_none_on_no_match():
    rows = [{"legal_1": "LAKESIDE", "page": "5"}]
    assert cs._pick_plat_page(rows, "IDLEWILD") is None


def test_pick_plat_page_empty_rows():
    assert cs._pick_plat_page([], "IDLEWILD") is None


# ------------------------------------------------------------------ _save_pdf


def _png_bytes(color=(255, 0, 0)):
    """Build a tiny valid 1x1 PNG in-memory so PIL can read it."""
    import zlib

    def _chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(
            ">I", zlib.crc32(c) & 0xFFFFFFFF
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1 RGB
    raw = b"\x00" + bytes(color)
    idat = zlib.compress(raw)
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def test_save_pdf_combines_pages(tmp_path):
    png1 = _png_bytes((255, 0, 0))
    png2 = _png_bytes((0, 255, 0))
    out = tmp_path / "out.pdf"
    name = cs._save_pdf([png1, png2], out)
    assert name == "out.pdf"
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF")


def test_save_pdf_filters_invalid_images(tmp_path):
    good = _png_bytes()
    bad = b"not an image"
    out = tmp_path / "out2.pdf"
    name = cs._save_pdf([bad, good], out)
    assert name == "out2.pdf"
    assert out.read_bytes().startswith(b"%PDF")


def test_save_pdf_no_valid_images_returns_none(tmp_path):
    assert cs._save_pdf([b"garbage"], tmp_path / "x.pdf") is None
