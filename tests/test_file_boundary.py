"""T-164: file boundary and write semantics.

The T-138 boundary was closed over `_known_roots()`, but that set included
scan roots -- which can be whole drives (`V:\\`). A scan root is discovery
scope, not file-access scope: nothing the viewer may read or write may be
reached through it. This locks the boundary to verified project roots and
locks write semantics to encoding/newline-preserving atomic replacement.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.api import Api
from saipenview.config import DEFAULTS
from saipenview.paths import canonical
from saipenview.service import SaipenViewService

pytestmark = pytest.mark.skipif(
    __import__("conftest", fromlist=["canonical_home"]).canonical_home() is None,
    reason="canonical SAIPEN home unreachable (protocol writes are journaled "
    "through it)",
)

# ── Fixtures (mirror tests/test_api.py's mocking, without importing it) ──


@pytest.fixture
def api(tmp_path) -> Api:
    cfg = dict(DEFAULTS)
    cfg["pinned_roots"] = []
    cfg["hidden_roots"] = []
    cfg["scan_roots"] = None
    with (
        patch("saipenview.api.config_path"),
        patch("saipenview.api.load_config", return_value=cfg),
        patch("saipenview.api.save_config"),
        patch("saipenview.api.BackgroundScanner"),
    ):
        api = Api()
        try:
            yield api
        finally:
            api.stop()


def _seed_project(root: Path, state_bytes: bytes | None = None) -> Path:
    from conftest import canonical_home

    home = canonical_home()
    saipen = root / ".saipen"
    saipen.mkdir(parents=True, exist_ok=True)
    payload = state_bytes or b"---\nphase: DONE\ntask: none\n---\n"
    # The canonical writer pipeline needs a resolvable saipen_home + a real
    # seat; inject them while preserving the seeded byte encoding/BOM/newline.
    if home is not None and b"saipen_home:" not in payload:
        import tempfile

        from saipenview import saio as _saio_mod

        fd, probe_name = tempfile.mkstemp()
        probe = Path(probe_name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        codec = _saio_mod._load_codec_from(home)
        doc = codec.read_document(probe)
        probe.unlink()
        text = doc.text_norm.replace(
            "---\n", f"---\nsaipen_home: '{home}'\nagent: testseat\n", 1
        )
        payload = doc.encode(text)
    (saipen / "STATE.md").write_bytes(payload)
    (saipen / "BOARD.md").write_text(
        "# BOARD\n\n## DOING\n\n## TODO\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
    )
    (saipen / "LOG.md").write_text(
        "- 11.08.26 00:00 [E-1] RUN: boot\n", encoding="utf-8"
    )
    return root


def _register(api: Api, root: Path) -> Path:
    api._config["pinned_roots"] = [str(root)]
    return root


class TestScanRootIsNotFileAccess:
    def test_scan_root_grants_no_read_access(self, api, tmp_path):
        """A bare scan root (whole dir with no .saipen/STATE.md) grants nothing."""
        api._config["scan_roots"] = [str(tmp_path)]
        secret = tmp_path / "secret.md"
        secret.write_text("secret\n", encoding="utf-8")
        assert api.read_file_text(str(secret)) is None
        assert api.write_file_text(str(secret), "pwned") is False
        assert secret.read_text(encoding="utf-8") == "secret\n"

    def test_scan_root_does_not_make_actions_work(self, api, tmp_path):
        """open_folder etc. refuse a root that is only a scan root."""
        api._config["scan_roots"] = [str(tmp_path)]
        with patch("os.startfile") as mock:
            assert api.open_folder(str(tmp_path)) is False
            mock.assert_not_called()

    def test_pinned_root_without_state_md_is_rejected(self, api, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        api._config["pinned_roots"] = [str(plain)]
        assert api.open_folder(str(plain)) is False


class TestVerifiedRootAccess:
    def test_protocol_files_readable_under_verified_root(self, api, tmp_path):
        root = _register(api, _seed_project(tmp_path / "proj"))
        board = root / ".saipen" / "BOARD.md"
        assert api.read_file_text(str(board)) is not None

    def test_unknown_root_is_controlled_error(self, api, tmp_path):
        _seed_project(tmp_path / "proj")  # has STATE.md but is not registered
        with patch("os.startfile") as mock:
            assert api.open_folder(str(tmp_path / "proj")) is False
            mock.assert_not_called()
        assert api.get_diff(str(tmp_path / "proj")) == {
            "ok": False,
            "error": "unknown or unverified project root",
        }

    def test_sibling_project_rejected(self, api, tmp_path):
        _register(api, _seed_project(tmp_path / "alpha"))
        sibling = _seed_project(tmp_path / "beta")
        assert api.read_file_text(str(sibling / ".saipen" / "STATE.md")) is None

    def test_dot_dot_escape_rejected(self, api, tmp_path):
        _register(api, _seed_project(tmp_path / "alpha"))
        target = tmp_path / "alpha" / ".." / "outside.md"
        target.write_text("x\n", encoding="utf-8")
        assert api.read_file_text(str(target)) is None


class TestWritePreservesEncodingAndNewline:
    def test_utf16le_is_preserved(self, api, tmp_path):
        raw = "---\nphase: DONE\ntask: none\n---\n".encode("utf-16-le")
        root = _register(api, _seed_project(tmp_path / "proj", raw))
        f = root / ".saipen" / "STATE.md"
        read = api.read_file_text(str(f))
        assert isinstance(read, dict) and "edit_version" in read
        assert (
            api.write_file_text(
                str(f), "---\nphase: BUILD\ntask: T-1\n---\n", read["edit_version"]
            )
            is True
        )
        assert f.read_bytes() == "---\nphase: BUILD\ntask: T-1\n---\n".encode(
            "utf-16-le"
        )

    def test_utf8_bom_is_preserved(self, api, tmp_path):
        raw = b"\xef\xbb\xbf" + b"---\nphase: DONE\n---\n"
        root = _register(api, _seed_project(tmp_path / "proj", raw))
        f = root / ".saipen" / "STATE.md"
        read = api.read_file_text(str(f))
        assert isinstance(read, dict) and "edit_version" in read
        assert (
            api.write_file_text(
                str(f), "---\nphase: BUILD\n---\n", read["edit_version"]
            )
            is True
        )
        assert f.read_bytes() == b"\xef\xbb\xbf" + b"---\nphase: BUILD\n---\n"

    def test_crlf_is_preserved(self, api, tmp_path):
        raw = b"---\r\nphase: DONE\r\ntask: none\r\n---\r\n"
        root = _register(api, _seed_project(tmp_path / "proj", raw))
        f = root / ".saipen" / "STATE.md"
        read = api.read_file_text(str(f))
        assert isinstance(read, dict) and "edit_version" in read
        assert (
            api.write_file_text(
                str(f), "---\r\nphase: BUILD\r\n---\r\n", read["edit_version"]
            )
            is True
        )
        assert f.read_bytes() == b"---\r\nphase: BUILD\r\n---\r\n"

    def test_new_file_defaults_to_utf8_lf(self, api, tmp_path):
        root = _register(api, _seed_project(tmp_path / "proj"))
        f = root / ".saipen" / "MANIFEST.md"
        assert api.write_file_text(str(f), "- sub -- x\n") is True
        assert f.read_bytes() == b"- sub -- x\n"


class TestAtomicWriteFailure:
    def test_simulated_replace_failure_leaves_original_byte_identical(
        self, api, tmp_path
    ):
        root = _register(api, _seed_project(tmp_path / "proj"))
        f = root / ".saipen" / "STATE.md"
        seeded = f.read_bytes()  # the conformant seeded bytes (saipen_home added)
        read = api.read_file_text(str(f))
        assert isinstance(read, dict) and "edit_version" in read
        with patch("os.replace", side_effect=OSError("disk full")):
            assert (
                api.write_file_text(
                    str(f), "---\nphase: BUILD\n---\n", read["edit_version"]
                )
                is False
            )
        # The original bytes survived; the failed commit left a recoverable
        # journal (nothing applied -> recovery aborts it cleanly).
        assert f.read_bytes() == seeded
        from saipenview.protocol_write import get_coordinator

        rec = get_coordinator().recover(root)
        assert rec.get("ok") is True, rec
        assert f.read_bytes() == seeded

    def test_no_temp_debris_after_failed_write(self, api, tmp_path):
        root = _register(api, _seed_project(tmp_path / "proj"))
        f = root / ".saipen" / "STATE.md"
        read = api.read_file_text(str(f))
        assert isinstance(read, dict) and "edit_version" in read
        with patch("os.replace", side_effect=OSError("disk full")):
            api.write_file_text(str(f), "x\n", read["edit_version"])
        # The original file was never replaced.
        assert "phase: DONE" in f.read_text(encoding="utf-8")


class TestSymlinkEscape:
    @pytest.mark.skipif(
        os.name == "nt" and not hasattr(os, "symlink"),
        reason="no symlink privilege on this Windows host",
    )
    def test_symlink_escape_rejected(self, api, tmp_path):
        _register(api, _seed_project(tmp_path / "proj"))
        outside = tmp_path / "secret.md"
        outside.write_text("secret\n", encoding="utf-8")
        link = tmp_path / "proj" / ".saipen" / "link.md"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation failed on this host")
        # canonical() resolves the symlink to its target, which lives outside
        # every verified root, so the boundary must reject it.
        assert api.read_file_text(str(link)) is None


class TestStateDeletionFailsClosed:
    """T-840 / W2-002: a cached verified root that lost its .saipen/STATE.md
    must fail the file boundary closed -- the PERF-009 cache may keep the root
    authorized until the next registry revision, but a dead project grants
    neither reads nor writes."""

    @staticmethod
    def _prime(api: Api, target: Path) -> dict:
        # First access primes the PERF-009 verified-roots cache with the root
        # alive; the deletion below must NOT invalidate that cache (we only
        # delete STATE.md, never call refresh/scan), so a pass proves the
        # resolver re-stat rather than a cache miss.
        read = api.read_file_text(str(target))
        assert read is not None  # cache primed with the root live
        return read

    def test_state_deletion_blocks_read_and_write_md(self, api, tmp_path):
        root = _register(api, _seed_project(tmp_path / "proj"))
        f = root / "notes.md"
        f.write_text("x\n", encoding="utf-8")
        read = self._prime(api, f)
        (root / ".saipen" / "STATE.md").unlink()
        assert api.read_file_text(str(f)) is None
        assert (
            api.write_file_text(str(f), "pwned\n", read["edit_version"], True)
            is False
        )
        assert f.read_text(encoding="utf-8") == "x\n"  # bytes unchanged

    def test_state_deletion_blocks_read_and_write_json(self, api, tmp_path):
        root = _register(api, _seed_project(tmp_path / "proj"))
        f = root / "data.json"
        f.write_text("{}", encoding="utf-8")
        read = self._prime(api, f)
        (root / ".saipen" / "STATE.md").unlink()
        assert api.read_file_text(str(f)) is None
        assert (
            api.write_file_text(str(f), '{"pwned":1}', read["edit_version"], True)
            is False
        )
        assert f.read_text(encoding="utf-8") == "{}"

    def test_live_root_still_reads_and_writes_after_peer_died(self, api, tmp_path):
        dead = _seed_project(tmp_path / "dead")
        live = _seed_project(tmp_path / "live")
        api._config["pinned_roots"] = [str(dead), str(live)]
        (dead / "notes.md").write_text("d\n", encoding="utf-8")
        f = live / "notes.md"
        f.write_text("l\n", encoding="utf-8")
        self._prime(api, f)  # cache holds both roots
        (dead / ".saipen" / "STATE.md").unlink()
        # The still-live project keeps ordinary CAS read/write.
        read = api.read_file_text(str(f))
        assert read is not None
        assert api.write_file_text(str(f), "l2\n", read["edit_version"], True)
        assert f.read_text(encoding="utf-8") == "l2\n"

    def test_restored_state_does_not_grant_access_from_unknown_root(
        self, api, tmp_path
    ):
        # Restoring STATE.md must not grant access from a root the registry
        # does not know -- authorization comes from the verified set, not from
        # the filesystem alone. Deregister first, restore second: still denied
        # until normal verification (a scan/pin) puts the root back.
        root = _register(api, _seed_project(tmp_path / "proj"))
        f = root / "notes.md"
        f.write_text("s\n", encoding="utf-8")
        self._prime(api, f)
        state = root / ".saipen" / "STATE.md"
        backup = state.read_bytes()
        state.unlink()
        api._config["pinned_roots"] = []  # the root is now unknown
        state.write_bytes(backup)  # STATE restored on disk
        assert api.read_file_text(str(f)) is None
        assert api.write_file_text(str(f), "pwned\n", None, None) is False
        assert f.read_text(encoding="utf-8") == "s\n"


class TestNestedRootAuthority:
    """T-840 / W2-002: with nested registered roots, the LONGEST containing
    cached root owns the file. A dead child must not inherit access from a
    live parent, and a dead ancestor must not shadow a deeper live project."""

    @staticmethod
    def _prime(api: Api, target: Path) -> dict:
        read = api.read_file_text(str(target))
        assert read is not None
        return read

    def test_dead_child_fails_closed_under_live_parent(self, api, tmp_path):
        parent = _seed_project(tmp_path / "parent")
        nested = _seed_project(parent / "nested")
        api._config["pinned_roots"] = [str(parent), str(nested)]
        f = nested / "notes.md"
        f.write_text("x\n", encoding="utf-8")
        read = self._prime(api, f)  # both roots cached, cache primed
        (nested / ".saipen" / "STATE.md").unlink()
        assert api.read_file_text(str(f)) is None
        assert (
            api.write_file_text(str(f), "pwned\n", read["edit_version"], True)
            is False
        )
        assert f.read_text(encoding="utf-8") == "x\n"

    def test_live_child_survives_dead_ancestor(self, api, tmp_path):
        parent = _seed_project(tmp_path / "parent")
        nested = _seed_project(parent / "nested")
        api._config["pinned_roots"] = [str(parent), str(nested)]
        f = nested / "notes.md"
        f.write_text("x\n", encoding="utf-8")
        read = self._prime(api, f)  # both roots cached, cache primed
        (parent / ".saipen" / "STATE.md").unlink()
        # resolver must pick the deepest live root, not the dead ancestor
        boundary = api._resolve_verified_root_for_file(str(f))
        assert boundary is not None and boundary.root == canonical(str(nested))
        assert api.read_file_text(str(f)) is not None
        assert api.write_file_text(str(f), "y\n", read["edit_version"], True) is True
        assert f.read_text(encoding="utf-8") == "y\n"


class TestNestedProtocolFileBoundary:
    """CORE-002: protocol-file ownership must stay on the verified boundary.

    ``root_for`` can discover a physical nested ``.saipen`` tree that the
    registry has never verified. It is a consistency check after the file
    boundary has selected an owner, never an alternate authorization source.
    """

    def test_unregistered_nested_protocol_read_is_rejected(self, api, tmp_path):
        outer = _seed_project(tmp_path / "outer")
        nested = _seed_project(outer / "nested")
        _register(api, outer)

        outer_board = outer / ".saipen" / "BOARD.md"
        nested_board = nested / ".saipen" / "BOARD.md"
        assert api.read_file_text(str(outer_board)) is not None
        assert api._resolve_verified_root_for_file(str(nested_board)).root == canonical(
            str(outer)
        )

        # The physical nearest .saipen belongs to `nested`, but only `outer`
        # is registered. Reading through that unverified ownership split must
        # fail closed.
        assert api.read_file_text(str(nested_board)) is None

    def test_unregistered_nested_write_cannot_escape_outer_agent_ownership(
        self, api, tmp_path
    ):
        from saipenview import saio
        from saipenview.protocol_write import get_coordinator

        outer = _seed_project(tmp_path / "outer")
        nested = _seed_project(outer / "nested")
        _register(api, outer)
        target = nested / ".saipen" / "STATE.md"
        seeded = target.read_bytes()
        doc = saio.engine(nested)["codec"].read_document(target)
        changed = doc.text_norm.replace("phase: DONE", "phase: BUILD")
        assert changed != doc.text_norm

        coordinator = get_coordinator()
        with coordinator.locked(outer):
            assert coordinator.ownership.reserve_agent(outer)
        try:
            assert (
                api.write_file_text(
                    str(target), changed, doc.raw_hash, existed=True
                )
                is False
            )
        finally:
            coordinator.ownership.release_agent(outer)

        assert target.read_bytes() == seeded

    def test_registered_nested_protocol_uses_inner_boundary_and_ownership(
        self, api, tmp_path, monkeypatch
    ):
        from saipenview import saio
        from saipenview.protocol_write import get_coordinator

        outer = _seed_project(tmp_path / "outer")
        nested = _seed_project(outer / "nested")
        api._config["pinned_roots"] = [str(outer), str(nested)]
        target = nested / ".saipen" / "STATE.md"
        boundary = api._resolve_verified_root_for_file(str(target))
        assert boundary is not None
        assert boundary.root == canonical(str(nested))

        coordinator = get_coordinator()
        engine_roots: list[str] = []
        mutation_roots: list[str] = []
        root_checks: list[str] = []
        real_engine = saio.engine
        real_mutate = coordinator.mutate
        real_root_for = coordinator.root_for

        def track_engine(root):
            engine_roots.append(canonical(str(root)))
            return real_engine(root)

        def track_mutate(root, *args, **kwargs):
            mutation_roots.append(canonical(str(root)))
            return real_mutate(root, *args, **kwargs)

        def track_root_for(path):
            root_checks.append(canonical(str(path)))
            return real_root_for(path)

        monkeypatch.setattr(saio, "engine", track_engine)
        monkeypatch.setattr(coordinator, "mutate", track_mutate)
        monkeypatch.setattr(coordinator, "root_for", track_root_for)

        read = api.read_file_text(str(target))
        assert isinstance(read, dict)
        assert engine_roots == [boundary.root]
        assert root_checks == [canonical(str(target))]
        changed = read["text"].replace("phase: DONE", "phase: BUILD")
        assert changed != read["text"]
        assert (
            api.write_file_text(
                str(target), changed, read["edit_version"], existed=True
            )
            is True
        )
        assert mutation_roots == [boundary.root]

        # Registered inner ownership is independently enforced; it is not
        # accidentally treated as the outer project's ownership slot.
        latest = api.read_file_text(str(target))
        assert isinstance(latest, dict)
        with coordinator.locked(nested):
            assert coordinator.ownership.reserve_agent(nested)
        try:
            assert (
                api.write_file_text(
                    str(target), latest["text"], latest["edit_version"], existed=True
                )
                is False
            )
        finally:
            coordinator.ownership.release_agent(nested)


class TestProtocolFileLiveness:
    """T-840 / W2-002: protocol-file read/write must also fail closed when the
    owning project's STATE.md is gone, before the coordinator/CAS pipeline
    ever plans a mutation."""

    def test_protocol_read_write_refused_after_state_loss(self, api, tmp_path):
        root = _register(api, _seed_project(tmp_path / "proj"))
        board = root / ".saipen" / "BOARD.md"
        read = api.read_file_text(str(board))
        assert isinstance(read, dict) and read["edit_version"]
        seeded = board.read_bytes()
        (root / ".saipen" / "STATE.md").unlink()
        assert api.read_file_text(str(board)) is None
        assert (
            api.write_file_text(
                str(board), "pwned\n", read["edit_version"], True
            )
            is False
        )
        assert board.read_bytes() == seeded


class TestBoundaryPerfWarmCache:
    """T-840 / PERF-009: on a warm verified-roots cache, one file access must
    stat .saipen/STATE.md only for the single authoritative matched root, not
    for every cached root."""

    def test_warm_access_stats_only_authoritative_root(self, api, tmp_path):
        alpha = _seed_project(tmp_path / "alpha")
        beta = _seed_project(tmp_path / "beta")
        gamma = _seed_project(tmp_path / "gamma")
        api._config["pinned_roots"] = [str(alpha), str(beta), str(gamma)]
        f = beta / "notes.md"
        f.write_text("x\n", encoding="utf-8")
        assert api.read_file_text(str(f)) is not None  # cold: cache built

        state_targets: list[Path] = []
        real_is_file = Path.is_file

        def spy_is_file(self):
            p = Path(self)
            if p.name.lower() == "state.md" and p.parent.name == ".saipen":
                state_targets.append(p)
            return real_is_file(self)

        patch.object(Path, "is_file", spy_is_file).start()
        try:
            # warm read: verified_roots() returns cache, resolver stats 1 STATE
            assert api.read_file_text(str(f)) is not None
            assert len(state_targets) == 1, state_targets
            assert state_targets[0] == Path(canonical(str(beta))) / ".saipen" / "STATE.md"
            # second warm read: one more STATE stat, still exactly one per call
            assert api.read_file_text(str(f)) is not None
            assert len(state_targets) == 2
        finally:
            patch.object(Path, "is_file", spy_is_file).stop()


class TestOrdinaryFileBaselineCas:
    def _ordinary_file(self, api: Api, tmp_path: Path) -> tuple[Path, Path]:
        root = _register(api, _seed_project(tmp_path / "ordinary-cas"))
        target = root / "notes.md"
        target.write_text("baseline\n", encoding="utf-8")
        return root, target

    def test_token_with_omitted_existed_commits_existing_baseline(
        self, api, tmp_path
    ):
        _, target = self._ordinary_file(api, tmp_path)
        read = api.read_file_text(str(target))
        assert read is not None and read["existed"] is True

        assert api.write_file_text(str(target), "updated\n", read["edit_version"])
        assert target.read_text(encoding="utf-8") == "updated\n"

    def test_omitted_existed_stale_token_refuses_external_change(self, api, tmp_path):
        _, target = self._ordinary_file(api, tmp_path)
        read = api.read_file_text(str(target))
        assert read is not None
        target.write_text("external\n", encoding="utf-8")

        assert (
            api.write_file_text(str(target), "stale editor\n", read["edit_version"])
            is False
        )
        assert target.read_text(encoding="utf-8") == "external\n"

    def test_omitted_existed_token_refuses_deleted_file_without_resurrection(
        self, api, tmp_path
    ):
        _, target = self._ordinary_file(api, tmp_path)
        read = api.read_file_text(str(target))
        assert read is not None
        target.unlink()

        assert (
            api.write_file_text(str(target), "must not reappear\n", read["edit_version"])
            is False
        )
        assert not target.exists()

    def test_missing_baseline_refuses_file_that_appeared(self, api, tmp_path):
        root, target = self._ordinary_file(api, tmp_path)

        assert api.write_file_text(str(target), "create\n", None, existed=False) is False
        assert target.read_text(encoding="utf-8") == "baseline\n"

    def test_tokenless_legacy_write_still_works(self, api, tmp_path):
        _, target = self._ordinary_file(api, tmp_path)

        assert api.write_file_text(str(target), "legacy write\n", None, None) is True
        assert target.read_text(encoding="utf-8") == "legacy write\n"

    def test_service_dispatch_accepts_token_without_optional_existed(
        self, api, tmp_path
    ):
        _, target = self._ordinary_file(api, tmp_path)
        read = api.read_file_text(str(target))
        assert read is not None
        service = SaipenViewService(auto_scan=False)
        service._api = api
        with service._rpc_cond:
            service._state = "running"
            service._rpc_admission_open = True

        try:
            # This is the RPC argument shape from older clients: existed is
            # omitted, so the optional fourth Api argument keeps its default.
            assert (
                service._dispatch(
                    "write_file_text",
                    [str(target), "rpc update\n", read["edit_version"]],
                )
                is True
            )
        finally:
            with service._rpc_cond:
                service._rpc_admission_open = False
                service._state = "stopped"

        assert target.read_text(encoding="utf-8") == "rpc update\n"
