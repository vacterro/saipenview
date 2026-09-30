"""T-172 + T-832/T-833: the .saipen persistence contract holds.

One contract, two halves (docs/saipen-persistence.md). Machine state is
local-only: nothing under `.saipen/` that names this machine or this session is
tracked. Two written exceptions travel via git, committed by the release
executor — the immutable audit receipts, and the closure commit that carries the
canonical memory so a released tag can run recovery from a fresh clone.

These tests pin the mechanical half: each tracked exception IS tracked, every
other `.saipen/` path stays ignored, and no machine-local absolute path reaches
the repository through a surface that is not an audit receipt.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# The written exceptions, verbatim from the contract's tables. Anything else
# under `.saipen/` is machine-local and must stay untracked.
_TRAVELS = (
    ".saipen/IDENTITY.md",  # CORE-004 lineage carrier (never had a path in it)
    ".saipen/intake/",
    ".saipen/archive/source/",
    ".saipen/kitchen/release_scope/",
    ".saipen/STATE.md",  # closure travel (T-832)
    ".saipen/BOARD.md",  # closure travel (T-832)
    ".saipen/LOG.md",  # closure travel (T-832)
    ".saipen/logs/",  # sealed segments (T-832)
    ".saipen/kitchen/digest.md",
    ".saipen/kitchen/release_receipt.json",
)
# Tracked own-`.saipen` CI snapshot: mechanically generated and sanitized, so
# the validator can run in a checkout whose live memory is gitignored.
_SNAPSHOT_PREFIX = "tests/fixtures/own_saipen_snapshot/"

# Receipt prose may quote the machine paths the audit observed; that is inert
# description, not live state. Only non-receipt surfaces must stay path-free.
_RECEIPT_PREFIXES = (".saipen/intake/", ".saipen/archive/", ".saipen/kitchen/")


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False
    )


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git not available",
)
class TestPersistenceContract:
    def test_closure_travel_is_not_ignored(self):
        """The canonical memory travels via the CLOSURE COMMIT (T-832), so the
        ignore rule must NOT swallow it — an ignore here would silently drop
        the E-### history a released tag needs to run recovery."""
        r = _git("check-ignore", "--no-index", ".saipen/BOARD.md")
        assert r.stdout.strip() == "", (
            ".saipen/BOARD.md is ignored; the closure-travel exception in "
            f".gitignore is negated somewhere: {r.stdout!r}"
        )

    def test_machine_local_saipen_state_stays_ignored(self):
        for rel in (
            ".saipen/recovery/x.json",
            ".saipen/saitranslate/x.json",
            ".saipen/KNOWLEDGE/x.md",
            ".saipen/extensions/subs/x/y.md",
        ):
            r = _git("check-ignore", "--no-index", rel)
            assert r.returncode == 0, (
                f"{rel} is no longer machine-local -- it would enter the "
                "repository carrying this machine's paths"
            )

    def test_no_saipen_files_tracked_beyond_the_contract(self):
        tracked = _git("ls-files").stdout.splitlines()
        banned = []
        for p in tracked:
            if not p.startswith(".saipen"):
                continue
            if p.startswith(_SNAPSHOT_PREFIX):
                continue
            if any(p == t or p.startswith(t) for t in _TRAVELS):
                continue
            banned.append(p)
        assert not banned, (
            "tracked .saipen/ content outside the written contract "
            "(docs/saipen-persistence.md):\n" + "\n".join(banned[:10])
        )
        snapshot = [p for p in tracked if p.startswith(_SNAPSHOT_PREFIX)]
        assert snapshot, "the tracked own-.saipen CI snapshot is missing"

    def test_the_contract_exceptions_are_actually_tracked(self):
        """A written exception that is not tracked is a contract that lies."""
        tracked = set(_git("ls-files").stdout.splitlines())
        for prefix in (".saipen/intake/", ".saipen/archive/source/"):
            assert any(p.startswith(prefix) for p in tracked), f"{prefix} travels per the contract but is untracked"

    def test_no_absolute_local_paths_in_tracked_content(self):
        # The ban is on MACHINE STATE, not prose: docstrings may say
        # `C:\Program Files` for illustration. Machine state lives in
        # saipenview/_data/ (config.json, cache.json) -- both must be entirely
        # absent from the tracked tree. Under .saipen/ only immutable audit
        # receipts and the canonical memory travel, and a receipt is allowed to
        # quote the machine paths the audit observed.
        tracked = _git("ls-files").stdout.splitlines()
        assert not [p for p in tracked if "saipenview/_data/" in p], (
            "runtime config/cache is tracked -- machine paths would leak"
        )
        data_files = [
            p
            for p in tracked
            if p.lower().endswith(".json") and not p.startswith("tests/")
        ]
        bad = []
        for rel in data_files:
            if rel.startswith(_RECEIPT_PREFIXES) or rel == ".saipen/kitchen/digest.md":
                continue  # receipt/digest prose may quote observed paths
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
            for match in re.findall(r"(?<![A-Za-z0-9])[A-Za-z]:\\", text):
                bad.append(f"{rel}: {match}")
        assert not bad, (
            "tracked JSON data carries absolute local drive paths:\n"
            + "\n".join(bad[:5])
        )

    def test_the_contract_document_exists_and_is_tracked(self):
        doc = ROOT / "docs" / "saipen-persistence.md"
        assert doc.is_file(), "the persistence contract document is missing"
        r = _git("ls-files", "--error-unmatch", "docs/saipen-persistence.md")
        assert r.returncode == 0, "the contract document itself must travel in git"
