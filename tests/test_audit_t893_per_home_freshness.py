"""T-893 (IMP-003): the multi-home contamination guard was process-global and
terminal, so one viewer process could serve exactly one SAIPEN home.

`_load_freshness_from` refused any home but the first the process touched,
forever. A viewer open on two projects whose STATE.md declare different
`saipen_home` values therefore failed every freshness/identity call for the
second project -- permanently, for the life of the process, decided by which
project the operator happened to open first.

The root cause is the NAME: `importlib.import_module("freshness")` binds
`freshness` in a process-global sys.modules, and whichever home reached it first
kept it. `tools/freshness.py` imports nothing from saipen_engine, so each home
can own its own module object under a home-scoped name. The guard that remains
refuses a name already bound to a different file -- contamination, not projects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saipenview import saio

_FRESHNESS_TEMPLATE = """
TAG = {tag!r}

def compute_source_identity(root):
    return "FROM-" + TAG

def compute_role_revision(path):
    return "FROM-" + TAG

def compute_generic_role_revision(path):
    return "FROM-" + TAG
"""


def _home(tmp_path: Path, name: str) -> Path:
    home = tmp_path / name
    (home / "tools").mkdir(parents=True)
    (home / "tools" / "freshness.py").write_text(
        _FRESHNESS_TEMPLATE.format(tag=name), encoding="utf-8"
    )
    return home


@pytest.fixture(autouse=True)
def clean_process():
    """A process that has touched no SAIPEN home.

    The guard under test is process-global, so the test cannot inherit a cache
    or a bound module name from whatever ran before it. Teardown restores the
    shared state other suites may hold.
    """
    saved_cache = dict(saio._ENGINE_CACHE)
    saved_modules = {
        n: m
        for n, m in __import__("sys").modules.items()
        if n.startswith("saipen_freshness_")
    }
    saio._ENGINE_CACHE.clear()
    for n in saved_modules:
        del __import__("sys").modules[n]
    try:
        yield
    finally:
        saio._ENGINE_CACHE.clear()
        saio._ENGINE_CACHE.update(saved_cache)
        for n in [
            n
            for n in __import__("sys").modules
            if n.startswith("saipen_freshness_")
        ]:
            del __import__("sys").modules[n]
        __import__("sys").modules.update(saved_modules)


def test_both_homes_resolve_freshness_in_one_process(tmp_path):
    a, b = _home(tmp_path, "INSTALL-A"), _home(tmp_path, "INSTALL-B")

    mod_a = saio._load_freshness_from(a)
    mod_b = saio._load_freshness_from(b)

    assert mod_a.compute_role_revision(tmp_path) == "FROM-INSTALL-A"
    assert mod_b.compute_role_revision(tmp_path) == "FROM-INSTALL-B"


def test_each_home_gets_its_own_module_object(tmp_path):
    a, b = _home(tmp_path, "INSTALL-A"), _home(tmp_path, "INSTALL-B")

    mod_a = saio._load_freshness_from(a)
    mod_b = saio._load_freshness_from(b)

    assert mod_a is not mod_b
    assert Path(mod_a.__file__).resolve() == (a / "tools" / "freshness.py").resolve()
    assert Path(mod_b.__file__).resolve() == (b / "tools" / "freshness.py").resolve()


def test_a_home_reloads_as_the_same_object(tmp_path):
    a = _home(tmp_path, "INSTALL-A")

    first = saio._load_freshness_from(a)
    second = saio._load_freshness_from(a)

    assert first is second


def test_no_first_touched_wins_ordering_survives_a_restart(tmp_path):
    """The same pairing must come out whichever order the homes are touched,
    in this process and in a fresh one -- otherwise the verdict is a property of
    the operator's click order, which is exactly what T-893 was filed about."""
    a, b = _home(tmp_path, "INSTALL-A"), _home(tmp_path, "INSTALL-B")

    a_then_b = (
        saio._load_freshness_from(a).compute_role_revision(tmp_path),
        saio._load_freshness_from(b).compute_role_revision(tmp_path),
    )
    saio._ENGINE_CACHE.clear()
    b_then_a = (
        saio._load_freshness_from(b).compute_role_revision(tmp_path),
        saio._load_freshness_from(a).compute_role_revision(tmp_path),
    )

    assert a_then_b == ("FROM-INSTALL-A", "FROM-INSTALL-B")
    assert b_then_a == ("FROM-INSTALL-B", "FROM-INSTALL-A")


def test_a_bound_name_is_refused_not_rebound(tmp_path):
    """The guard survives for the case it still means something: an alias that
    already answers for a DIFFERENT file must be a refusal, not a silent
    overwrite."""
    a, b = _home(tmp_path, "INSTALL-A"), _home(tmp_path, "INSTALL-B")
    key = saio._home_key(a)
    saio._load_freshness_from(a)

    # Point A's alias at B's file, then ask for A again.
    import sys

    sys.modules[saio._freshness_alias(key)] = saio._load_freshness_from(b)
    saio._ENGINE_CACHE.clear()

    with pytest.raises(saio.SaioUnavailable, match="MULTI-HOME CONTAMINATION BLOCKED"):
        saio._load_freshness_from(a)


def test_a_broken_freshness_module_leaves_nothing_bound(tmp_path):
    """A module that raises at import must not answer identity questions on the
    next call. An unbound name is a clean refusal; a bound broken one is a wrong
    answer."""
    home = _home(tmp_path, "INSTALL-BROKEN")
    (home / "tools" / "freshness.py").write_text(
        "raise RuntimeError('this install is half-installed')\n", encoding="utf-8"
    )

    with pytest.raises(RuntimeError):
        saio._load_freshness_from(home)

    import sys

    assert saio._freshness_alias(saio._home_key(home)) not in sys.modules