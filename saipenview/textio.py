"""One reader for every `.saipen/` file this viewer opens.

`read_text(encoding="utf-8")` was used everywhere until this module existed,
and it has two failure modes on real projects, both of which this viewer hit
on its own `.saipen/STATE.md`:

* **UTF-16.** `Set-Content` / `Out-File` on Windows PowerShell 5.1 writes
  UTF-16LE by default. `read_text(encoding="utf-8")` raises
  `UnicodeDecodeError`, the scanner logs it as an unreadable project and drops
  the row. The project vanishes from the list with no explanation -- which is
  how this viewer came to be unable to display the project it lives in.

* **A UTF-8 BOM.** This one is worse, because nothing raises. `utf-8` (as
  opposed to `utf-8-sig`) keeps the BOM as a leading `﻿`, so the first
  line reads `﻿---` instead of `---`, the frontmatter regex does not
  match, and `parse_frontmatter` returns an empty dict. The project renders as
  phase `?` with no fields and no error anywhere.

So: sniff the BOM, fall back through utf-8 and cp1251, and only then decode
lossily. Never raise on content -- a background scan thread under
`pythonw.exe` has no console to raise into.
"""

from __future__ import annotations

import codecs
from pathlib import Path

# Longest BOM first: UTF-32LE starts with the same two bytes as UTF-16LE, so
# checking UTF-16 first would mis-sniff every UTF-32LE file.
_BOMS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)


def _bomless_utf16(raw: bytes) -> str | None:
    """Name the UTF-16 variant of a BOM-less file, or None if it isn't one.

    This exists because the obvious check does not work: UTF-16LE ASCII text
    is every other byte NUL, and NUL is a perfectly valid UTF-8 character, so
    `raw.decode("utf-8")` SUCCEEDS on it and returns a string full of NULs.
    Nothing raises, the frontmatter regex quietly fails to match, and the file
    reports itself as clean UTF-8. Caught exactly that way: this viewer's own
    STATE.md was rewritten BOM-less, `encoding_of` called it utf-8, and the
    project rendered with no fields at all.

    So test what UTF-16 actually looks like -- NUL bytes packed into one
    parity of the offsets -- rather than whether a decoder complains.
    """
    if len(raw) < 4 or b"\x00" not in raw:
        return None
    head = raw[: 4096 - (4096 % 2)]
    even_nul = head[0::2].count(0)
    odd_nul = head[1::2].count(0)
    half = len(head) // 2
    if not half:
        return None
    # Latin text in UTF-16LE puts the NUL in the odd (high) byte, UTF-16BE in
    # the even one. Genuine UTF-8 has no NULs at all in practice, so any strong
    # one-sided majority is the giveaway.
    if odd_nul > half * 0.3 and even_nul < half * 0.1:
        return "utf-16-le"
    if even_nul > half * 0.3 and odd_nul < half * 0.1:
        return "utf-16-be"
    return None


def decode(raw: bytes) -> str:
    """Decode `.saipen/` file bytes to text, never raising.

    Returns text with the BOM stripped and CRLF normalised to LF, so callers
    can match `^---` and `^## TODO` without caring where the file came from.
    """
    for bom, enc in _BOMS:
        if raw.startswith(bom):
            text = raw[len(bom) :].decode(enc, errors="replace")
            break
    else:
        bomless = _bomless_utf16(raw)
        if bomless:
            text = raw.decode(bomless, errors="replace")
        else:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                # cp1251 before latin-1: these files are frequently Russian,
                # and latin-1 cannot fail, so putting it first would mean
                # cp1251 is never reached and Cyrillic always arrives as
                # mojibake.
                try:
                    text = raw.decode("cp1251")
                except UnicodeDecodeError:
                    text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_doc(path: Path | str) -> str:
    """Read one `.saipen/` document. Missing or unreadable file -> empty string.

    Unreadable must not propagate: this runs on the scan thread, once per
    project per sweep, and one locked or deleted file must not end the sweep.
    """
    try:
        return decode(Path(path).read_bytes())
    except OSError:
        return ""


def read_doc_meta(path: Path | str) -> tuple[str, str, str]:
    """Read a document this viewer is about to WRITE BACK.

    Returns `(text, encoding, newline)` so `write_doc` can put it back exactly
    as it was found. The viewer edits one line of a file it did not author --
    moving a ticket, stamping `updated` -- and must not turn that into a
    whole-file re-encoding. A UTF-16 `.saipen/` file is a real defect and the
    conformance check says so loudly, but fixing it is the user's decision to
    make, not a side effect of clicking a ticket.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return "", "utf-8", "\n"
    for bom, enc in _BOMS:
        if raw.startswith(bom):
            text = raw[len(bom) :].decode(enc, errors="replace")
            break
    else:
        bomless = _bomless_utf16(raw)
        # The `-nobom` suffix is not a codec name -- write_doc strips it and
        # takes it as "encode as this, but emit no BOM". Without it the two
        # cases are indistinguishable on the way back out and a BOM-carrying
        # file silently loses its BOM the first time one field is stamped.
        enc = (bomless + "-nobom") if bomless else "utf-8"
        if bomless:
            text = raw.decode(bomless, errors="replace")
        else:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text, enc = raw.decode("cp1251"), "cp1251"
                except UnicodeDecodeError:
                    text = raw.decode("utf-8", errors="replace")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), enc, newline


def write_doc(
    path: Path | str, text: str, encoding: str = "utf-8", newline: str = "\n"
) -> None:
    """Write a `.saipen/` document atomically, in the given encoding.

    Temp file plus `os.replace`, because the earlier plain write left a
    truncated file when it was interrupted and the next start choked on it.
    The temp name is unique per call (T-164: no two writers race over one
    shared ``<name>.tmp``) and is removed in ``finally`` so a failed encode or
    a failed ``os.replace`` cannot leave debris -- and a failed write never
    touches the target, so the original stays byte-identical.
    Takes the encoding names `read_doc_meta` hands back, including its
    `-nobom` suffix. The UTF-16 and UTF-32 codecs named with an explicit byte
    order do NOT emit a BOM of their own, so writing back what was read from a
    BOM-carrying file has to prepend it here -- otherwise stamping one field
    quietly converts the file to the BOM-less form, which is precisely the
    shape `_bomless_utf16` exists to catch.
    """
    import os
    import stat
    import tempfile

    path = Path(path)
    if newline != "\n":
        text = text.replace("\n", newline)
    codec, no_bom = encoding, False
    if codec.endswith("-nobom"):
        codec, no_bom = codec[: -len("-nobom")], True
    raw = text.encode(codec, errors="replace")
    if not no_bom:
        for bom, enc in _BOMS:
            # utf-8-sig writes its own BOM; only the byte-order-explicit
            # UTF-16/32 codecs need one prepended.
            if enc == codec and not raw.startswith(bom):
                raw = bom + raw
                break
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        if path.exists():
            try:
                os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
            except OSError:
                pass
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def encoding_of(path: Path | str) -> str:
    """Name the encoding `read_doc` would use, for reporting.

    The conformance check flags anything that is not plain UTF-8: a UTF-16 or
    BOM-carrying `.saipen/` file is readable *here* but is exactly what
    `tools/validate.py` and the portable `grep`-based floor choke on, so the
    project is broken for every other tool even while this viewer shows it.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return "unreadable"
    for bom, enc in _BOMS:
        if raw.startswith(bom):
            return enc
    bomless = _bomless_utf16(raw)
    if bomless:
        return bomless + " (no BOM)"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return "not-utf-8"
    return "utf-8"
