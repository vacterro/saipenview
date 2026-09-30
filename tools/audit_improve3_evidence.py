"""Evidence for T-917 and T-918 (IMPROVE cycle imp-vacterro-saipenview-20260930-3).

Drives the REAL SaipenWatcher, the REAL Api attribution path and the REAL
coordinator, over real files, and measures the two things the core audit
found. No event_count is synthesised: every count reported here was published
by the platform's own observer.

  T-917  a single commit publishes MORE filesystem notifications than the
         number of self-write registrations the coordinator arms, so
         Api._on_file_changed reports `origin == "external"` for the app's
         own write.
  T-918  armed registrations outlive their notification, so a leaked entry
         stays fingerprint-addressable and absorbs a later external change
         that produces the same bytes.

EXIT SEMANTICS. This script exits 0 when it has REPRODUCED the characterised
defect -- that is what makes it evidence for the two tickets. It exits 1 once
the defect is gone, because then the tickets' evidence is stale and they must
be re-evaluated rather than quietly closed. It is not a pass/fail gate on
correct behaviour; `pytest tests/test_watcher_attribution.py` is that.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saipenview import api as api_mod  # noqa: E402
from saipenview import events as events_mod  # noqa: E402
from saipenview.protocol_write import get_coordinator  # noqa: E402
from saipenview.watcher import SaipenWatcher  # noqa: E402

#: Debounce long enough that every write in a run lands in one window, which
#: is the coordinator's ordinary behaviour (one commit writes STATE, BOARD
#: and LOG back to back).
WINDOW_DEBOUNCE = 0.6
SETTLE = 1.5
AFTER_WRITE = 1.0


def _project(tmp: Path) -> tuple[Path, Path]:
    root = tmp / "proj"
    (root / ".saipen").mkdir(parents=True)
    target = root / ".saipen" / "STATE.md"
    target.write_text("phase: DONE\n", encoding="utf-8")
    return root, target


def measure_notifications(writes: int = 4) -> dict:
    """Notifications published per write, for both write shapes.

    `os.replace` is the shape the canonical journal commits with (temp file
    plus atomic replace), so it is the production number; `write_text` is
    measured too because a plain editor write reaches the same guard.
    """
    counts: dict[str, list[int]] = {"os_replace": [], "write_text": []}
    with tempfile.TemporaryDirectory() as td:
        root, target = _project(Path(td))
        seen: list[int] = []
        events_mod.event_bus.subscribe(
            "saipen.project_changed",
            lambda d: seen.append(int(d.get("event_count") or 0)),
        )
        wch = SaipenWatcher(debounce_delay=0.4)
        wch.sync([str(root)], [str(root)])
        time.sleep(SETTLE)

        def run(shape: str, body: str) -> int:
            mark = len(seen)
            if shape == "os_replace":
                tmp = target.with_suffix(".md.tmp")
                tmp.write_text(body, encoding="utf-8")
                os.replace(tmp, target)
            else:
                target.write_text(body, encoding="utf-8")
            time.sleep(AFTER_WRITE)
            return max(seen[mark:]) if len(seen) > mark else 0

        for i in range(writes):
            counts["os_replace"].append(run("os_replace", f"phase: A{i}\n"))
        for i in range(writes):
            counts["write_text"].append(run("write_text", f"phase: P{i}\n"))
        wch.stop()
    return counts


def measure_attribution(writes: int = 3) -> dict:
    """What Api._on_file_changed decides for the app's own writes, and how
    many registrations are left armed afterwards."""
    origins: list[tuple[str, str, str]] = []
    api_mod.event_bus.subscribe(
        "saipen.file_changed",
        lambda d: origins.append((d.get("root"), d.get("file"), d.get("origin"))),
    )
    with tempfile.TemporaryDirectory() as td:
        root, target = _project(Path(td))
        coord = get_coordinator()
        api = api_mod.Api(debounce_delay=30.0)
        api.start()  # subscribes _on_file_changed
        wch = SaipenWatcher(debounce_delay=WINDOW_DEBOUNCE)
        wch.sync([str(root)], [str(root)])
        time.sleep(SETTLE)

        for i in range(writes):
            target.write_text(f"phase: W{i}\n", encoding="utf-8")
            coord.finalize_self_writes(
                root,
                [".saipen/STATE.md"],
                fingerprints={".saipen/STATE.md": coord.fingerprint(target)},
            )
            time.sleep(0.05)
        time.sleep(SETTLE)
        leaked = coord.self_writes.count(str(root), "STATE.md")
        wch.stop()
        api.stop()
    mine = [(f, o) for r, f, o in origins if r == str(root)]
    return {
        "writes": writes,
        "origins": mine,
        "reported_self": sum(1 for _, o in mine if o == "self"),
        "reported_external": sum(1 for _, o in mine if o == "external"),
        "armed_left_over": leaked,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args(argv)

    notes = measure_notifications()
    attribution = measure_attribution()

    # T-917: notifications per commit exceed the one registration armed.
    t917 = any(n >= 2 for n in notes["os_replace"]) and (
        attribution["reported_external"] > attribution["reported_self"]
    )
    # T-918: registrations outlive the notifications that should have
    # consumed them.
    t918 = attribution["armed_left_over"] > 0

    report = {
        "platform": sys.platform,
        "notifications_per_commit": notes,
        "registrations_armed_per_commit": 1,
        "attribution": attribution,
        "T-917_reproduced": t917,
        "T-918_reproduced": t918,
        "reproduced": bool(t917 or t918),
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("T-917/T-918 evidence -- real watcher, real Api, real coordinator")
        print(f"  platform                       : {report['platform']}")
        print(f"  notifications per os.replace   : {notes['os_replace']}")
        print(f"  notifications per write_text   : {notes['write_text']}")
        print(f"  registrations armed per commit : 1")
        print(f"  app-write origins              : {attribution['origins']}")
        print(
            f"  self / external                : {attribution['reported_self']}"
            f" / {attribution['reported_external']}"
        )
        print(f"  armed registrations left over  : {attribution['armed_left_over']}")
        print(f"  T-917 reproduced               : {t917}")
        print(f"  T-918 reproduced               : {t918}")

    if report["reproduced"]:
        print(
            "REPRODUCED: the characterised defect is still present; "
            "T-917 and T-918 keep their evidence."
        )
        return 0
    print(
        "NOT REPRODUCED: the defect is gone (or the platform does not exhibit "
        "it). Re-evaluate T-917 and T-918 before closing them."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
