#!/usr/bin/env python
"""Project-local conformance validator entry (canonical ship-gate shape).

SAIPENVIEW ships as a consumer of the SAIPEN protocol, not as a vendored
copy of it (docs/saipen-persistence.md, T-172): the engine lives in the
machine-local protocol home and is deliberately NOT tracked in git. The
protocol's ship phase (`phases/ship.md`, step 6b) nevertheless runs the
project-local `tools/validate.py` as the binding pre-commit gate, and the
canonical dogfood project satisfies that by committing the validator itself.

This repository resolves that tension with a thin locator wrapper: it finds
the installed protocol home the same way `tools/install_hook.py` does
(SAIPEN_HOME environment variable first, then STATE.md's `saipen_home`
field), re-executes the canonical validator there, and delegates its exit
code. No protocol logic is duplicated here, so the gate can never drift from
the installed engine; and no machine path is hardcoded, so the wrapper stays
clone-stable by construction.

The protocol home is resolved at RUNTIME by explicit, auditable steps -- it
is never silently defaulted from this wrapper's own location.

Stdlib only -- no pip installs, ever.
"""

import os
import re
import sys
from pathlib import Path


def _protocol_home() -> Path:
    """Resolve the SAIPEN protocol home exactly like install_hook.py.

    1. ``SAIPEN_HOME`` environment variable, when it points at a live
       ``tools/validate.py``;
    2. the machine-local ``saipen_home`` field recorded in the project's own
       ``.saipen/STATE.md``.

    Anything else is a hard refusal: guessing would let a stale or wrong
    protocol version authorize a release.
    """
    env = os.environ.get("SAIPEN_HOME", "").strip()
    if env:
        candidate = Path(env)
        if (candidate / "tools" / "validate.py").is_file():
            return candidate

    state = Path(".saipen/STATE.md")
    if state.is_file():
        match = re.search(
            r'(?m)^saipen_home:[ \t]*"?\/?([^\r\n"]+?)"?[ \t]*\r?$', state.read_text(encoding="utf-8-sig")
        )
        if match:
            candidate = Path(match.group(1).strip())
            if (candidate / "tools" / "validate.py").is_file():
                return candidate

    sys.stderr.write(
        "FAIL: cannot resolve the SAIPEN protocol home.\n"
        "Set SAIPEN_HOME to the protocol install (it must contain "
        "tools/validate.py) or run `saipen set` so .saipen/STATE.md "
        "records saipen_home.\n"
    )
    sys.exit(2)


def main() -> int:
    home = _protocol_home()
    validator = home / "tools" / "validate.py"
    # Validation is a read-only gate (install_hook.py purity guard, gen 5):
    # GIT_OPTIONAL_LOCKS=0 stops git's *read* commands from opportunistically
    # refreshing the index behind the caller's back, so running the gate can
    # never rewrite index bytes the release executor snapshots around it.
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    completed = __import__("subprocess").run(
        [sys.executable, str(validator), *sys.argv[1:]], env=env
    )
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
