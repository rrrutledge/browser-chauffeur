"""Debug logging to a rotating-free flat file (best effort, never raises)."""
import os
from datetime import datetime

LOG_FILE = os.path.expanduser('~/.claude/hook-debug.log')


def log_debug(message):
    """Append a timestamped debug line; silently ignore any failure."""
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass
