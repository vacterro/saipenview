"""Encoding sniffing, including the two shapes that used to pass silently."""

from __future__ import annotations

import codecs

import pytest

from saipenview.textio import decode, encoding_of, read_doc, read_doc_meta, write_doc

SAMPLE = "---\nphase: DONE\ntask: none\n---\n"


def _write(tmp_path, name, raw: bytes):
    p = tmp_path / name
    p.write_bytes(raw)
    return p


class TestDecode:
    def test_plain_utf8(self):
        assert decode(SAMPLE.encode("utf-8")) == SAMPLE

    def test_utf8_bom_is_stripped(self):
        # The quiet one: utf-8 (not utf-8-sig) keeps the BOM as a leading
        # character, so `^---` stops matching and the frontmatter silently
        # parses as empty.
        assert decode(codecs.BOM_UTF8 + SAMPLE.encode("utf-8")) == SAMPLE

    def test_utf16_le_with_bom(self):
        assert decode(codecs.BOM_UTF16_LE + SAMPLE.encode("utf-16-le")) == SAMPLE

    def test_utf16_be_with_bom(self):
        assert decode(codecs.BOM_UTF16_BE + SAMPLE.encode("utf-16-be")) == SAMPLE

    def test_utf16_le_without_bom(self):
        # The one that fooled the first version of this module: UTF-16LE ASCII
        # is every other byte NUL, NUL is valid UTF-8, so .decode("utf-8")
        # SUCCEEDS and returns a NUL-riddled string that matches nothing.
        assert decode(SAMPLE.encode("utf-16-le")) == SAMPLE

    def test_utf16_be_without_bom(self):
        assert decode(SAMPLE.encode("utf-16-be")) == SAMPLE

    def test_crlf_normalised(self):
        assert decode(b"a\r\nb\r\n") == "a\nb\n"

    def test_cp1251_cyrillic_survives(self):
        text = "next_action: ждём\n"
        assert decode(text.encode("cp1251")) == text

    def test_never_raises_on_garbage(self):
        assert isinstance(decode(bytes(range(256))), str)


class TestEncodingOf:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (SAMPLE.encode("utf-8"), "utf-8"),
            (codecs.BOM_UTF8 + SAMPLE.encode("utf-8"), "utf-8-sig"),
            (codecs.BOM_UTF16_LE + SAMPLE.encode("utf-16-le"), "utf-16-le"),
            (SAMPLE.encode("utf-16-le"), "utf-16-le (no BOM)"),
            (SAMPLE.encode("utf-16-be"), "utf-16-be (no BOM)"),
        ],
    )
    def test_names_the_encoding(self, tmp_path, raw, expected):
        assert encoding_of(_write(tmp_path, "STATE.md", raw)) == expected

    def test_missing_file(self, tmp_path):
        assert encoding_of(tmp_path / "nope.md") == "unreadable"


class TestReadDoc:
    def test_missing_file_is_empty(self, tmp_path):
        assert read_doc(tmp_path / "nope.md") == ""

    def test_directory_is_empty_not_raise(self, tmp_path):
        assert read_doc(tmp_path) == ""


class TestRoundTrip:
    @pytest.mark.parametrize(
        "raw",
        [
            SAMPLE.encode("utf-8"),
            codecs.BOM_UTF8 + SAMPLE.encode("utf-8"),
            codecs.BOM_UTF16_LE + SAMPLE.encode("utf-16-le"),
            SAMPLE.replace("\n", "\r\n").encode("utf-8"),
        ],
    )
    def test_write_preserves_what_read_found(self, tmp_path, raw):
        # Editing one field must not re-encode a file the viewer did not
        # author: read_doc_meta -> write_doc is a byte-for-byte round trip.
        p = _write(tmp_path, "STATE.md", raw)
        text, enc, newline = read_doc_meta(p)
        write_doc(p, text, enc, newline)
        assert p.read_bytes() == raw

    def test_write_is_atomic_no_leftover_tmp(self, tmp_path):
        p = _write(tmp_path, "STATE.md", SAMPLE.encode("utf-8"))
        write_doc(p, "changed\n")
        assert not (tmp_path / "STATE.md.tmp").exists()
        assert p.read_text(encoding="utf-8") == "changed\n"
