"""T-189: the two dependency-install paths cannot silently disagree.

`pip install -r requirements.txt` (run.bat bootstrap) and the wheel build
(pyproject `dependencies`) must install the same supported runtime floor.
requirements.txt also carries nuitka, which must be declared in pyproject's
`dev` extra -- a build dependency, not a runtime one.
"""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 (the supported floor is >=3.10)
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent


def _parse_reqs(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, spec = line.partition(">=")
        out[name.strip().lower()] = ("", spec) if not spec else spec
    return out


def test_requirements_runtime_floor_matches_pyproject():
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    py_deps = {
        d.partition(">=")[0].strip().lower(): d.partition(">=")[2]
        for d in py["project"]["dependencies"]
    }
    reqs = _parse_reqs((ROOT / "requirements.txt").read_text(encoding="utf-8"))

    runtime_reqs = {k: v for k, v in reqs.items() if k != "nuitka"}
    assert set(py_deps) == set(runtime_reqs), (
        f"runtime packages differ: pyproject={set(py_deps)} reqs={set(runtime_reqs)}"
    )
    for name in py_deps:
        assert py_deps[name] == runtime_reqs[name], (
            f"floor for {name} differs: pyproject>={py_deps[name]} "
            f"requirements>={runtime_reqs[name]}"
        )


def test_nuitka_is_a_dev_extra_not_a_runtime_dep():
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = {d.partition(">=")[0].strip().lower() for d in py["project"]["dependencies"]}
    assert "nuitka" not in deps, "nuitka is a build dependency, not a runtime floor"
    extras = py["project"].get("optional-dependencies", {})
    dev = " ".join(extras.get("dev", []))
    assert "nuitka" in dev.lower(), "nuitka must be declared in the dev extra"
