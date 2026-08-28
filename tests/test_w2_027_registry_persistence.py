"""T-37 / W2-027: ExternalChangeRegistry process lifetime persistence.

Registry safety evidence existed only in module-global in-memory dict.
Recording unresolved entry then recreating/reloading registry removed it;
no persistence/load path. collect_outbox_entry relies on registry as
mutation safety boundary. Restart implicitly acknowledges every unexplained
external change.

Fix: persist unresolved entries atomically to _data/external_changes.json.
Load on construction; save on every record/acknowledge.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.external_changes import ExternalChangeRegistry, get_registry, _registry


@pytest.fixture
def clean_registry(tmp_path: Path):
    """Return a registry with isolated persist path and no leftover state."""
    import saipenview.external_changes as ec

    # Reset module-level singleton and token counter
    ec._registry = None
    ec._next_token = 0

    reg = ExternalChangeRegistry()
    persist = tmp_path / f"ext_{uuid.uuid4().hex}.json"
    reg._set_persist_path(persist)
    yield reg
    # Cleanup singleton so next test starts fresh
    ec._registry = None
    ec._next_token = 0


def test_persistence_survives_recreation(clean_registry):
    """Record entry, recreate registry, entry still present."""
    reg = clean_registry
    token = reg.record("/root", "STATE.md", "fp1")

    # Recreate registry (simulates restart)
    reg2 = ExternalChangeRegistry()
    reg2._set_persist_path(reg._persist_path)
    pending = reg2.pending("/root")
    assert len(pending) == 1
    assert pending[0].token == token
    assert pending[0].rel_path == "STATE.md"
    assert pending[0].fingerprint == "fp1"


def test_acknowledge_persists_removal(clean_registry):
    """Acknowledge removes entry from disk."""
    reg = clean_registry
    token = reg.record("/root", "BOARD.md", "fp-a")

    reg.acknowledge("/root", "BOARD.md", token)

    reg2 = ExternalChangeRegistry()
    reg2._set_persist_path(reg._persist_path)
    assert reg2.pending("/root") == []


def test_new_record_overwrites_same_path(clean_registry):
    """New record for same path replaces old entry on disk."""
    reg = clean_registry
    t1 = reg.record("/root", "STATE.md", "fp-old")
    t2 = reg.record("/root", "STATE.md", "fp-new")

    reg2 = ExternalChangeRegistry()
    reg2._set_persist_path(reg._persist_path)
    pending = reg2.pending("/root")
    assert len(pending) == 1
    assert pending[0].token == t2
    assert pending[0].fingerprint == "fp-new"


def test_multiple_roots_all_persisted(clean_registry):
    """Entries for different roots all survive recreation."""
    reg = clean_registry
    reg.record("V:/root/a", "STATE.md", "fp1")
    reg.record("V:/root/b", "BOARD.md", "fp2")

    reg2 = ExternalChangeRegistry()
    reg2._set_persist_path(reg._persist_path)
    all_pending = reg2.pending()
    assert len(all_pending) == 2
    roots = {c.root for c in all_pending}
    assert "v:\\root\\a" in roots
    assert "v:\\root\\b" in roots
