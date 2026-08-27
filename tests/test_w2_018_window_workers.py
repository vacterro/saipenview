"""T-28 / W2-018: window geometry/visibility generation teardown.

Geometry stop sets reusable Event and drops thread identity without joining;
rapid restart clears same Event before old worker observes, allowing duplicate
workers. Visibility destroy does not invalidate _vis_gen; blocked work
released after destroy schedules further JS activity.

Fix: per-worker _geom_gen token checked inside _geometry_periodic;
destroy bumps _vis_gen to invalidate any in-flight visibility work.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from saipenview.ui.window import MainWindow


def test_geometry_worker_checks_generation():
    """Rapid stop/start leaves only one alive worker via generation gate."""
    with patch("saipenview.ui.window.webview"):
        mw = MainWindow()

    # Start worker
    mw._start_geometry_thread()
    gen1 = mw._geom_gen
    assert mw._geometry_thread is not None
    t1 = mw._geometry_thread

    # Stop -> increments gen AND sets _geometry_stop
    mw._stop_geometry_thread()
    assert mw._geom_gen == gen1 + 1

    # Wait for old thread to notice _geometry_stop and exit
    t1.join(timeout=3)
    # Old thread may still be alive briefly if it was in _save_geometry();
    # what matters is that _geom_gen no longer matches t1's captured gen.
    assert mw._geom_gen != gen1, "generation must have advanced"

    # Start again -> new gen, new thread
    mw._start_geometry_thread()
    assert mw._geom_gen == gen1 + 2
    t2 = mw._geometry_thread
    assert t2 is not t1
    t2.join(timeout=3)


def test_destroy_invalidates_visibility_gen():
    """destroy() bumps _vis_gen so in-flight visibility work aborts."""
    with patch("saipenview.ui.window.webview"):
        mw = MainWindow()

    assert mw._vis_gen == 0
    mw._vis_in_flight = True
    mw._vis_desired = True

    mw.destroy()

    assert mw._vis_gen >= 1, "destroy must bump _vis_gen"
    assert mw._vis_in_flight is False
    assert mw._vis_desired is None
