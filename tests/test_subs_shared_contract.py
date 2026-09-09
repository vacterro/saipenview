"""SubSaipen shared-contract staleness is the SYNCED surface, and only that.

`check_subs_staleness` compares this project's `.saipen/extensions/subs/` copies
against the home's, and the badge it drives means one thing: your local protocol
copy is behind. That claim is only true of files `saipen sub sync` refreshes --
`saipen_engine.subs._SHARED_FILES` (`PROTOCOL.md`, `README.md`, `crew.md`) plus
`_SHARED_DIRS` (`TEMPLATE/`).

`MANIFEST.md` was in the compared set and is why this file exists. The manifest
is per-project STATE: `sub spawn` appends the new instance and `sub collect`
records `last_collect: <digest>@<time>` on the line. So the moment a project
spawned a sub or collected a package it reported stale forever -- `sub sync`
refreshed two other files and changed nothing about the verdict, because the
engine does not sync the manifest and never will. Measured on this repository:
five spawned instances and four `last_collect` markers, permanent stale.

`crew.md` was NOT in the compared set, which is the same defect at the opposite
polarity: v7.251.0 added a 35-line applicability section to it and this project
carried the pre-applicability copy while the badge said fresh.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saipenview.parser import _STALENESS_FILES, check_subs_staleness

#: `saipen_engine.subs._SHARED_FILES` + `_SHARED_DIRS`, as of 7.252.0. Named
#: here so the assertion states the contract rather than restating the code.
ENGINE_SHARED_FILES = ("PROTOCOL.md", "README.md", "crew.md")
ENGINE_SHARED_DIRS = ("TEMPLATE",)
TEMPLATE_MEMBERS = ("STATE.md", "BOARD.md", "LOG.md")


def _subs_pair(tmp_path: Path) -> tuple[Path, Path]:
    """A project and a home whose shared contract is byte-identical."""
    home = tmp_path / "home"
    canon = home / "extensions" / "subs"
    canon.mkdir(parents=True)
    root = tmp_path / "proj"
    local = root / ".saipen" / "extensions" / "subs"
    local.mkdir(parents=True)

    for name in ENGINE_SHARED_FILES:
        body = f"# {name}\n\ncanonical\n"
        (canon / name).write_text(body, encoding="utf-8")
        (local / name).write_text(body, encoding="utf-8")
    for parent in (canon, local):
        (parent / "TEMPLATE").mkdir()
        for member in TEMPLATE_MEMBERS:
            (parent / "TEMPLATE" / member).write_text(
                f"# {member}\n", encoding="utf-8"
            )
    # A manifest that legitimately differs: the project has spawned a sub and
    # collected from it. This is the state the old comparison called drift.
    (canon / "MANIFEST.md").write_text(
        "# SubSaipen Manifest\n\n- saiwiki -- .saipen/extensions/subs/saiwiki/\n",
        encoding="utf-8",
    )
    (local / "MANIFEST.md").write_text(
        "# SubSaipen Manifest\n\n"
        "- saiwiki -- .saipen/extensions/subs/saiwiki/ | last_collect: sha256:ab@1\n"
        "- myagent -- .saipen/extensions/subs/myagent/\n",
        encoding="utf-8",
    )
    return root, home


def _state(home: Path) -> dict:
    return {"saipen_home": str(home)}


class TestComparedSetMatchesTheEngine:
    def test_every_engine_shared_file_is_compared(self) -> None:
        for name in ENGINE_SHARED_FILES:
            assert name in _STALENESS_FILES, (
                f"{name} is refreshed by `saipen sub sync` but never compared, so a "
                f"real contract change reads as fresh"
            )

    def test_every_template_member_is_compared(self) -> None:
        for member in TEMPLATE_MEMBERS:
            assert f"TEMPLATE/{member}" in _STALENESS_FILES

    def test_the_manifest_is_not_compared(self) -> None:
        """Per-project state can never be drift.

        There is no command that clears it, so reporting it is a badge nobody
        can act on -- worse than silence, because it hides the real ones.
        """
        assert "MANIFEST.md" not in _STALENESS_FILES

    def test_nothing_outside_the_synced_surface_is_compared(self) -> None:
        allowed = {*ENGINE_SHARED_FILES, *(f"TEMPLATE/{m}" for m in TEMPLATE_MEMBERS)}
        assert set(_STALENESS_FILES) <= allowed, (
            f"compared files outside the synced surface: "
            f"{sorted(set(_STALENESS_FILES) - allowed)}"
        )


class TestVerdicts:
    def test_matching_contract_with_a_diverged_manifest_is_fresh(self, tmp_path) -> None:
        root, home = _subs_pair(tmp_path)
        assert check_subs_staleness(root, _state(home)) == (False, "")

    @pytest.mark.parametrize("name", ENGINE_SHARED_FILES)
    def test_a_changed_shared_file_is_stale(self, tmp_path, name) -> None:
        root, home = _subs_pair(tmp_path)
        target = root / ".saipen" / "extensions" / "subs" / name
        target.write_text(target.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")
        stale, details = check_subs_staleness(root, _state(home))
        assert stale is True
        assert name in details
        assert "content differs" in details

    def test_crew_md_drift_is_reported(self, tmp_path) -> None:
        """The case this project actually shipped in.

        `crew.md` gained the applicability section in 7.251.0. Without it in the
        compared set the local copy could sit a release behind and the badge
        would say fresh -- which is what happened here.
        """
        root, home = _subs_pair(tmp_path)
        (home / "extensions" / "subs" / "crew.md").write_text(
            "# crew.md\n\ncanonical\n\n## Applicability\n\nnew section\n",
            encoding="utf-8",
        )
        stale, details = check_subs_staleness(root, _state(home))
        assert stale is True
        assert "crew.md" in details

    def test_a_missing_local_shared_file_is_stale(self, tmp_path) -> None:
        root, home = _subs_pair(tmp_path)
        (root / ".saipen" / "extensions" / "subs" / "crew.md").unlink()
        stale, details = check_subs_staleness(root, _state(home))
        assert stale is True
        assert "missing locally" in details

    def test_no_home_is_not_stale(self, tmp_path) -> None:
        root, _home = _subs_pair(tmp_path)
        assert check_subs_staleness(root, {}) == (False, "")

    def test_unreachable_home_is_not_stale(self, tmp_path) -> None:
        """A home this machine does not have is unknown, never behind."""
        root, _home = _subs_pair(tmp_path)
        assert check_subs_staleness(root, {"saipen_home": str(tmp_path / "nope")}) == (
            False,
            "",
        )
