import subprocess, sys, time, tempfile, pathlib, os
import ctypes
from ctypes import wintypes

helper = pathlib.Path(__file__).parent / "tests" / "fixtures" / "heartbeat_child.py"
child = subprocess.Popen([sys.executable, str(helper), str(pathlib.Path(tempfile.gettempdir()) / "hb_dbg.txt")],
                         cwd=str(pathlib.Path(".").resolve()))
time.sleep(0.5)

k = ctypes.windll.kernel32
HANDLE = wintypes.HANDLE
k.CreateJobObjectW.restype = HANDLE
k.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
k.SetInformationJobObject.restype = wintypes.BOOL
k.SetInformationJobObject.argtypes = [HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
k.AssignProcessToJobObject.restype = wintypes.BOOL
k.AssignProcessToJobObject.argtypes = [HANDLE, HANDLE]
k.CloseHandle.restype = wintypes.BOOL
k.CloseHandle.argtypes = [HANDLE]

class JOBINFO(ctypes.Structure):
    _fields_ = [
        ("a", ctypes.c_int64), ("b", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("c", ctypes.c_size_t), ("d", ctypes.c_size_t),
        ("e", wintypes.DWORD),
        ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
        ("f", wintypes.DWORD), ("g", wintypes.DWORD),
    ]

h_job = k.CreateJobObjectW(None, None)
print("CreateJobObjectW ->", h_job, "err", k.GetLastError())
info = JOBINFO()
info.LimitFlags = 0x2000
ok = k.SetInformationJobObject(h_job, 2, ctypes.byref(info), ctypes.sizeof(info))
print("SetInformationJobObject ->", ok, "err", k.GetLastError(), "sizeof", ctypes.sizeof(info))
ph = HANDLE(int(child._handle))
ok2 = k.AssignProcessToJobObject(h_job, ph)
print("AssignProcessToJobObject ->", ok2, "err", k.GetLastError())
print("child alive before job close:", child.poll() is None)
k.CloseHandle(h_job)
time.sleep(1.0)
print("child alive after job handle close:", child.poll() is None)
child.kill()
print("done")
