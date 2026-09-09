"""T-801 / PERF-002: durable-cache sidecar loading is single-pass and linear.

The ticket claims "parse each sidecar once, O(1) digest lookups, O(N) total
canonicalization", and the tree it shipped kept only the first of those. The
deletion path re-hashed EVERY known root for EVERY dropped digest, so a cold
start -- the one moment when every tombstone is applied -- paid quadratic
canonicalization: measured 650 / 2500 / 9800 ``_canonical_or`` calls for 40 /
80 / 160 rows with half of them tombstoned. Nothing in the suite looked at
that, so the claim was untested rather than wrong-and-caught.

`_canonical_or` is not free: it resolves a filesystem path. On the cold start
this runs against a cache holding every project the machine has ever scanned.

The three claims, each stated so it can fail:

* every sidecar file is READ exactly once;
* canonicalization is O(rows), not O(rows x tombstones);
* the outcome is unchanged -- tombstoned rows leave, surviving rows stay, and a
  recreated root beats an older `.deleted` marker.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import saipenview.api as api_mod
from saipenview.api import Api, _canonical_or


def _row(root: str) -> dict:
    return {
        "root": root,
        "name": Path(root).name,
        "phase": "DONE",
        "is_pinned": False,
        "task": "none",
        "next_action": "",
        "blocker": "none",
        "mtime": 0,
        "updated": "",
        "updated_kind": "no-timestamp",
    }


def _digest(root: str) -> str:
    return hashlib.sha256(_canonical_or(root).encode("utf-8")).hexdigest()


def _loader(tmp_path: Path, rows: list[dict], sidecars: dict[str, dict]):
    """A bare Api carrying `rows`, with `sidecars` on disk beside its cache.

    Constructed with ``object.__new__`` deliberately: this exercises
    ``_load_cache_records`` as the pure cache-merge step it is, with no scan,
    no watcher and no process manager to perturb the counts being measured.
    """
    data = tmp_path / "_data"
    data.mkdir(parents=True, exist_ok=True)
    cache_file = data / "cache.json"
    cache_file.write_text(json.dumps(rows), encoding="utf-8")
    records = cache_file.with_name(cache_file.stem + "_records")
    records.mkdir(exist_ok=True)
    for filename, payload in sidecars.items():
        (records / filename).write_text(json.dumps(payload), encoding="utf-8")

    api = object.__new__(Api)
    api._projects = list(rows)
    api._cache_file = cache_file
    api._config = {}
    api._sort_order = lambda: "smart"
    return api, records


class TestEachSidecarIsReadOnce:
    def test_no_sidecar_is_read_twice(self, tmp_path, monkeypatch):
        """A second read of the same file is a second parse in disguise.

        Counted per path, so a loader that re-opened one sidecar to resolve a
        deletion would be caught even though the total read count still looked
        proportional.
        """
        roots = [str(tmp_path / f"p{i}") for i in range(6)]
        sidecars = {}
        for i, root in enumerate(roots):
            digest = _digest(root)
            sidecars[f"{digest}.json"] = (
                {Api._CACHE_DELETED_MARKER: True} if i % 2 else _row(root)
            )
        api, _records = _loader(tmp_path, [_row(r) for r in roots], sidecars)

        reads: dict[str, int] = {}
        real_read = Path.read_text

        def counting_read(self, *args, **kwargs):
            if self.suffix in (".json", ".deleted"):
                reads[self.name] = reads.get(self.name, 0) + 1
            return real_read(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", counting_read)
        api._load_cache_records()

        repeated = {name: n for name, n in reads.items() if n > 1}
        assert not repeated, f"sidecar(s) read more than once: {repeated}"


class TestCanonicalizationIsLinear:
    @pytest.mark.parametrize("n_rows", [40, 80, 160])
    def test_work_follows_row_count_not_row_count_times_tombstones(
        self, tmp_path, monkeypatch, n_rows
    ):
        """Half the rows tombstoned: the pre-fix loader paid rows x tombstones.

        The bound is generous on purpose (a small constant per row, not an
        exact count) so a legitimate refactor that canonicalizes a row twice
        stays green while the quadratic shape cannot: at 160 rows the old code
        performed 9800 canonicalizations against a bound of 640.
        """
        roots = [str(tmp_path / f"p{i}") for i in range(n_rows)]
        sidecars = {
            f"{_digest(root)}.json": {Api._CACHE_DELETED_MARKER: True}
            for root in roots[: n_rows // 2]
        }
        api, _records = _loader(tmp_path, [_row(r) for r in roots], sidecars)

        calls = {"n": 0}
        real = api_mod._canonical_or

        def counting(path):
            calls["n"] += 1
            return real(path)

        monkeypatch.setattr(api_mod, "_canonical_or", counting)
        api._load_cache_records()

        assert len(api._projects) == n_rows - n_rows // 2
        assert calls["n"] <= 4 * n_rows, (
            f"{calls['n']} canonicalizations for {n_rows} rows / "
            f"{n_rows // 2} tombstones -- superlinear in the tombstone count"
        )


class TestOutcomeIsUnchanged:
    def test_tombstone_drops_and_record_survives(self, tmp_path):
        keep = str(tmp_path / "keep")
        drop = str(tmp_path / "drop")
        api, _records = _loader(
            tmp_path,
            [_row(keep), _row(drop)],
            {
                f"{_digest(keep)}.json": _row(keep),
                f"{_digest(drop)}.json": {Api._CACHE_DELETED_MARKER: True},
            },
        )
        api._load_cache_records()
        assert [p["root"] for p in api._projects] == [keep]

    def test_legacy_deleted_marker_still_drops_its_row(self, tmp_path):
        """The two-file legacy shape is migrated, not ignored."""
        gone = str(tmp_path / "gone")
        api, records = _loader(tmp_path, [_row(gone)], {})
        (records / f"{_digest(gone)}.deleted").write_text("", encoding="utf-8")
        api._load_cache_records()
        assert api._projects == []

    def test_newer_record_beats_an_older_legacy_tombstone(self, tmp_path):
        """A root deleted and then recreated must come back.

        Recreation is the case a digest-keyed shortcut can silently break: the
        tombstone and the record share one digest, so only the mtime order
        separates "removed" from "removed then re-added".
        """
        import os
        import time

        root = str(tmp_path / "recreated")
        api, records = _loader(tmp_path, [], {})
        digest = _digest(root)
        (records / f"{digest}.deleted").write_text("", encoding="utf-8")
        time.sleep(0.01)
        record = records / f"{digest}.json"
        record.write_text(json.dumps(_row(root)), encoding="utf-8")
        os.utime(record, None)

        api._load_cache_records()
        assert [p["root"] for p in api._projects] == [root]
