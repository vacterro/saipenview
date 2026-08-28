"""T-43 / W2-033: _assign_job_object / successful process finalization native HANDLE leak.

Verifies: OpenProcess handle closed after assignment; Job handle closed once
during _finalize; _close_saipen_job_handle is safe when no handle is set.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


def test_close_handle_safe_when_none():
    """_close_saipen_job_handle must be a no-op when handle is absent."""
    from saipenview.runtime import _close_saipen_job_handle

    proc = MagicMock()
    if hasattr(proc, "_saipen_job_handle"):
        delattr(proc, "_saipen_job_handle")
    # Must not raise regardless of platform
    _close_saipen_job_handle(proc)


def test_assign_job_object_closes_openprocess_handle():
    """_assign_job_object must close the OpenProcess-created handle after
    AssignProcessToJobObject succeeds, keeping only the Job handle on proc."""
    from saipenview.runtime import _assign_job_object
    import ctypes
    from ctypes import wintypes

    proc = MagicMock()
    proc._handle = None
    proc.pid = 99999

    close_log = []

    def fake_close_handle(h):
        close_log.append(h)

    def fake_assign(h_job, h_proc):
        proc._saipen_job_handle = h_job
        return True

    # Patch at the ctypes level — _assign_job_object does `ctypes.windll.kernel32`
    mock_k32 = MagicMock()
    mock_k32.CreateJobObjectW.return_value = 0xABC
    mock_k32.SetInformationJobObject.return_value = True
    mock_k32.AssignProcessToJobObject.side_effect = fake_assign
    mock_k32.OpenProcess.return_value = 0xDEF
    mock_k32.CloseHandle.side_effect = fake_close_handle

    # Replace windll.kernel32 before calling
    orig_windll = ctypes.windll
    try:
        ctypes.windll.kernel32 = mock_k32
        _assign_job_object(proc)
    finally:
        ctypes.windll = orig_windll

    # OpenProcess must have been called once
    assert mock_k32.OpenProcess.call_count == 1
    # The OpenProcess handle (0xDEF) must be in close log
    assert 0xDEF in close_log, f"OpenProcess handle not closed; close_log={close_log}"
    # The Job handle (0xABC) must NOT be closed yet
    assert 0xABC not in close_log, "Job handle closed prematurely"
    # Job handle must be stashed on proc
    assert proc._saipen_job_handle == 0xABC


def test_finalize_closes_job_handle():
    """_close_saipen_job_handle must close the stashed Job handle and clear it."""
    from saipenview.runtime import _close_saipen_job_handle
    import ctypes

    proc = MagicMock()
    proc._saipen_job_handle = 0xCAFEBABE

    close_log = []

    mock_k32 = MagicMock()
    mock_k32.CloseHandle.side_effect = lambda h: close_log.append(h)

    orig_windll = ctypes.windll
    try:
        ctypes.windll.kernel32 = mock_k32
        _close_saipen_job_handle(proc)
    finally:
        ctypes.windll = orig_windll

    assert not hasattr(proc, "_saipen_job_handle"), "handle not cleared"
    assert len(close_log) == 1
    # CloseHandle receives a ctypes HANDLE (c_void_p); compare the raw value
    assert close_log[0].value == 0xCAFEBABE
