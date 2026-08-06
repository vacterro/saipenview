"""Tests for saipenview.paths — the canonical path layer (T-138)."""

from __future__ import annotations

from pathlib import Path

from saipenview.paths import (
    canonical,
    canonical_key,
    dedupe,
    is_inside,
    validate_file_path,
)


class TestCanonical:
    def test_lowercases_and_backslashes(self):
        assert canonical(r"C:\Foo\Bar") == r"c:\foo\bar"

    def test_trailing_slash_normalised_for_dir(self):
        assert canonical(r"c:\foo\bar" + "\\") == r"c:\foo\bar"

    def test_drive_root_keeps_trailing_slash(self):
        assert canonical(r"C:") == r"c:" + "\\"
        assert canonical("c:/") == r"c:" + "\\"

    def test_resolves_dot_dot(self):
        assert canonical(r"c:\foo\..\bar") == r"c:\bar"

    def test_relative_becomes_absolute(self, tmp_path):
        c = canonical(tmp_path)
        assert Path(c).is_absolute()


class TestCanonicalKey:
    def test_same_key_for_case_and_slash_variants(self):
        assert canonical_key(r"C:\Foo") == canonical_key("c:/foo")

    def test_drive_root_distinct_from_child(self):
        assert canonical_key(r"C:") != canonical_key(r"C:\x")


class TestDedupe:
    def test_case_and_slash_dupes_collapse(self):
        out = dedupe([r"C:\Foo", "c:/foo", r"C:\Bar"])
        assert len(out) == 2
        assert out[0] == r"c:\foo"

    def test_none_and_empty(self):
        assert dedupe(None) == []
        assert dedupe([]) == []

    def test_keeps_first_seen_order(self):
        out = dedupe([r"C:\B", r"C:\A", "c:/b"])
        assert out == [r"c:\b", r"c:\a"]


class TestIsInside:
    def test_child_is_inside(self):
        assert is_inside(r"C:\proj", r"C:\proj\.saipen\STATE.md")

    def test_root_itself(self):
        assert is_inside(r"C:\proj", r"C:\proj")

    def test_dot_dot_escape_rejected(self):
        assert not is_inside(r"C:\proj", r"C:\proj\..\other\file.md")

    def test_sibling_rejected(self):
        assert not is_inside(r"C:\proj", r"C:\proj2\file.md")

    def test_case_insensitive(self):
        assert is_inside(r"C:\PROJ", r"c:\proj\.saipen\BOARD.md")


class TestValidateFilePath:
    def test_md_inside_root_ok(self):
        ok, _ = validate_file_path(r"C:\proj\.saipen\STATE.md", [r"C:\proj"])
        assert ok

    def test_json_inside_root_ok(self):
        ok, _ = validate_file_path(r"C:\proj\.saipen\subs\s.json", [r"C:\proj"])
        assert ok

    def test_other_extension_rejected(self):
        ok, reason = validate_file_path(r"C:\proj\evil.exe", [r"C:\proj"])
        assert not ok
        assert "extension" in reason

    def test_path_escaping_root_rejected(self):
        ok, reason = validate_file_path(r"C:\proj\..\outside\secret.md", [r"C:\proj"])
        assert not ok
        assert "escapes" in reason

    def test_empty_known_roots_fails_closed(self):
        ok, reason = validate_file_path(r"C:\proj\STATE.md", [])
        assert not ok
        assert "no known roots" in reason

    def test_root_itself_is_a_file_under_it(self):
        ok, _ = validate_file_path(r"C:\proj\.saipen\STATE.md", [r"c:\proj"])
        assert ok
