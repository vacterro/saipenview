"""PERF-003 (SRC-018 R013 / T-843): zero-per-row presentation canonicalization.

The audited defect: get_projects() and get_hidden_projects() (and pin
membership) ran canonical()/_canonical_or() per row on every call. T-843's
model is: canonicalize ONCE at registry/cache ingress, store an internal
membership key on the row, and filter presentation retrieval from that
in-memory key.

Oracle: ingest 1000 rows, instrument the canonical resolver, and prove that
repeated get_projects / get_hidden_projects perform ZERO per-row resolver
calls, that an empty hidden set takes the zero-work path, that Api._lock is not
held across resolver latency, and that the internal key never leaks into public
transport.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import saipenview.api as api_mod
from saipenview.api import Api


@pytest.fixture(autouse=True)
def api_env(tmp_path, monkeypatch):
    cfg = {
        "scan_roots": [],
        "pinned_roots": [],
        "hidden_roots": [],
        "sort_order": "smart",
        "auto_scan": False,
        "rescan_interval": 300,
    }
    from saipenview.config import DEFAULTS

    merged = dict(DEFAULTS)
    merged.update(cfg)
    data_dir = tmp_path / "_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    with (
        patch("saipenview.api.config_path", return_value=data_dir / "config.json"),
        patch("saipenview.api.load_config", return_value=merged),
        patch("saipenview.api.save_config"),
        patch("saipenview.api.BackgroundScanner"),
    ):
        api = Api()
        api.stop()
        yield api, merged
        api.stop()


def _seed_rows(api, n: int) -> None:
    """Populate _projects directly with n ingress-canonicalized rows."""
    rows = []
    for i in range(n):
        root = f"V:\\proj{i}"
        # Rows enter through _project_to_dict at ingress; simulate that here by
        # storing the canonical membership key exactly as ingress would.
        rows.append(
            {
                "root": root,
                "_canon_key": api_mod._canonical_or(root),
                "name": f"proj{i}",
                "phase": "BUILD",
                "task": "",
                "blocker": "none",
                "updated": None,
                "updated_kind": None,
                "is_pinned": False,
                "git_branch": "",
                "git_dirty": False,
                "subs_stale": False,
                "conformance": {"verdict": "pass", "fails": 0, "warns": 0,
                                "baseline": "", "findings": []},
                "subs": [],
                "translate": None,
            }
        )
    with api._lock:
        api._projects = rows


def test_repeated_get_projects_zero_per_row_resolver(api_env):
    api, cfg = api_env
    _seed_rows(api, 1000)
    # Hide a handful so the filter path is exercised.
    cfg["hidden_roots"] = [api_mod._canonical_or("V:\\proj0"),
                           api_mod._canonical_or("V:\\proj1")]

    calls = {"n": 0}
    real = api_mod.canonical

    def counting_canonical(p):
        calls["n"] += 1
        return real(p)

    with patch("saipenview.api.canonical", side_effect=counting_canonical), \
         patch("saipenview.api._canonical_or", side_effect=lambda s: real(s)) as co:
        # Reset after any construction-time work.
        calls["n"] = 0
        co.reset_mock()
        result1 = api.get_projects()
        result2 = api.get_projects()

    assert len(result1) == 998  # 1000 - 2 hidden
    assert result1 == result2
    # ZERO per-row resolver calls: the hidden filter used stored _canon_key.
    assert co.call_count == 0, (
        f"get_projects made {co.call_count} per-row _canonical_or calls"
    )


def test_empty_hidden_set_zero_work_path(api_env):
    api, cfg = api_env
    _seed_rows(api, 1000)
    cfg["hidden_roots"] = []

    with patch("saipenview.api._canonical_or") as co:
        rows = api.get_projects()
    assert len(rows) == 1000
    # Empty hidden set: no filtering resolver work at all.
    assert co.call_count == 0


def test_repeated_get_hidden_projects_zero_per_row_resolver(api_env):
    api, cfg = api_env
    _seed_rows(api, 1000)
    hidden = [api_mod._canonical_or(f"V:\\proj{i}") for i in range(500)]
    cfg["hidden_roots"] = hidden

    with patch("saipenview.api._canonical_or") as co:
        rows1 = api.get_hidden_projects()
        rows2 = api.get_hidden_projects()
    assert len(rows1) == 500
    assert len(rows2) == 500
    assert co.call_count == 0, (
        f"get_hidden_projects made {co.call_count} per-row _canonical_or calls"
    )
    # The internal key never leaks into the transport rows.
    assert all("_canon_key" not in r for r in rows1)


def test_get_projects_does_not_hold_lock_across_resolver(api_env):
    """Ordinary retrieval must snapshot rows under the lock and then filter
    outside it -- never hold Api._lock across canonical() latency."""
    api, cfg = api_env
    _seed_rows(api, 100)
    cfg["hidden_roots"] = [api_mod._canonical_or("V:\\proj0")]

    lock_held_during_filter = {"held": False}
    real_canonical = api_mod._canonical_or

    def probing_canonical(s):
        # If the Api lock is held while this runs, the retrieval violated the
        # contract. acquire(blocking=False) returns False iff already held.
        acquired = api._lock.acquire(blocking=False)
        if acquired:
            api._lock.release()
        else:
            lock_held_during_filter["held"] = True
        return real_canonical(s)

    # Force the fallback path (rows without stored key) so _canonical_or runs.
    with api._lock:
        for p in api._projects:
            p.pop("_canon_key", None)

    with patch("saipenview.api._canonical_or", side_effect=probing_canonical):
        api.get_projects()

    assert lock_held_during_filter["held"] is False, (
        "Api._lock was held across the canonical resolver during get_projects"
    )


def test_internal_key_absent_from_public_transport(api_env):
    api, cfg = api_env
    _seed_rows(api, 10)
    projects = api.get_projects()
    assert all("_canon_key" not in p for p in projects)
    hidden_before = api.get_hidden_projects()
    assert hidden_before == []
