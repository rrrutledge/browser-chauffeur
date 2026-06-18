"""Windows presence gate for the drainer keeper.

The user is "present" when input has been idle less than a threshold AND the session is not
locked. The poller runs this first each cycle and skips all work when away — no window, no noise.
Idle comes from the Win32 GetLastInputInfo API; lock state from the LogonUI process (Windows runs
LogonUI.exe while the secure/lock screen is up — a common, dependency-free heuristic).

Used as a module by run-poller.py (`import presence; presence.is_present(threshold)`), or as a CLI:
    python presence.py [--threshold 600]   ->  prints "present"/"away ..." and exits 0/1.
"""
import ctypes
import sys
from ctypes import wintypes


def idle_seconds():
    """Seconds since the last keyboard/mouse input, or None if the API call fails."""
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    tick = ctypes.windll.kernel32.GetTickCount()
    return (tick - info.dwTime) / 1000.0


def is_locked():
    """True if the workstation is locked (LogonUI.exe present)."""
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]
    snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(entry)
    found = False
    if ctypes.windll.kernel32.Process32First(snap, ctypes.byref(entry)):
        while True:
            if entry.szExeFile.lower() == b"logonui.exe":
                found = True
                break
            if not ctypes.windll.kernel32.Process32Next(snap, ctypes.byref(entry)):
                break
    ctypes.windll.kernel32.CloseHandle(snap)
    return found


def is_present(threshold_seconds=600):
    """Return (present: bool, idle: float|None, locked: bool)."""
    idle = idle_seconds()
    locked = is_locked()
    present = (idle is not None) and (idle < threshold_seconds) and (not locked)
    return present, idle, locked


if __name__ == "__main__":
    threshold = 600
    if "--threshold" in sys.argv:
        threshold = int(sys.argv[sys.argv.index("--threshold") + 1])
    present, idle, locked = is_present(threshold)
    if present:
        print(f"present (idle {idle:.0f}s)")
        sys.exit(0)
    reason = "locked" if locked else f"idle {idle:.0f}s >= {threshold}s" if idle is not None else "idle unknown"
    print(f"away ({reason})")
    sys.exit(1)
