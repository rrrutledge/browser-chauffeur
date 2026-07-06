"""Live Windows process-ancestry lookup, used to prove a `taskkill /PID` target
is really "the terminal tab hosting this session" rather than trusting an
argument value.

Pure ctypes against kernel32's toolhelp snapshot API — no third-party
dependency (psutil may or may not be installed on a given machine; stdlib
always is). Any failure (wrong platform, API error, unexpected data, or an
ancestry shape we don't recognize) returns None so callers fail closed to a
manual prompt instead of guessing.
"""
import ctypes
import os
from ctypes import wintypes

TH32CS_SNAPPROCESS = 0x00000002
MAX_ANCESTOR_DEPTH = 32
# The Claude Code CLI's own process name — the anchor we climb from. Everything
# below this in the chain (the hook's shell wrapper, etc.) is uninteresting;
# everything above it (the WindowsTerminal.exe container, services.exe, ...) is
# shared infrastructure a single session must never be allowed to kill.
CLAUDE_PROCESS_NAME = 'claude.exe'


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('cntUsage', wintypes.DWORD),
        ('th32ProcessID', wintypes.DWORD),
        ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)),
        ('th32ModuleID', wintypes.DWORD),
        ('cntThreads', wintypes.DWORD),
        ('th32ParentProcessID', wintypes.DWORD),
        ('pcPriClassBase', wintypes.LONG),
        ('dwFlags', wintypes.DWORD),
        ('szExeFile', ctypes.c_char * 260),
    ]


def _snapshot():
    """Return {pid: (ppid, lowercase_exe_name)} for every running process, or
    {} on failure (wrong platform, API error)."""
    if os.name != 'nt':
        return {}
    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (0, -1):
        return {}
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        mapping = {}
        if not kernel32.Process32First(snapshot, ctypes.byref(entry)):
            return {}
        while True:
            name = entry.szExeFile.decode('mbcs', errors='replace').lower()
            mapping[entry.th32ProcessID] = (entry.th32ParentProcessID, name)
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
        return mapping
    finally:
        kernel32.CloseHandle(snapshot)


def self_tab_host_pid(start_pid=None, max_depth=MAX_ANCESTOR_DEPTH, snapshot=None):
    """Return the PID of the process that hosts THIS session's terminal
    tab/pane — the immediate parent of this session's own `claude.exe` process
    — or None if it can't be determined.

    This is the only PID a `taskkill` may safely self-target: never
    `claude.exe` itself (that's a snapshot key, not a host), never
    WindowsTerminal.exe (shared across every tab in the window), and never
    anything further up (services.exe, wininit.exe, the System process).
    Walks upward from `start_pid` (default: this process) live via the OS
    process table so the answer reflects current reality, not a cached or
    supplied value.
    """
    try:
        snap = snapshot if snapshot is not None else _snapshot()
        if not snap:
            return None
        current = os.getpid() if start_pid is None else start_pid
        seen = {current}
        for _ in range(max_depth):
            entry = snap.get(current)
            if not entry:
                return None
            ppid, name = entry
            if name == CLAUDE_PROCESS_NAME:
                return ppid if ppid and ppid not in seen else None
            if ppid == 0 or ppid in seen:
                return None
            seen.add(ppid)
            current = ppid
        return None
    except Exception:
        return None
