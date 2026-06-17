"""Load per-machine drainer settings from .claude/drainer.local.md (YAML frontmatter).

Single source of truth for everything machine/user-specific: local_dir, the channel
registry, outreach board config, cadence, presence. The engine/plugin stays generic;
this file is what each machine fills in. Credentials never live here — they come from
the environment / OS credential store.

Requires PyYAML for the frontmatter (pip install pyyaml).
"""
import os

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML is required to read .claude/drainer.local.md (pip install pyyaml).")


def _find_settings_file():
    """Walk up from CWD looking for .claude/drainer.local.md."""
    d = os.path.abspath(os.getcwd())
    while True:
        cand = os.path.join(d, ".claude", "drainer.local.md")
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            raise SystemExit("No .claude/drainer.local.md found (copy templates/drainer.local.example.md).")
        d = parent


def load_settings():
    path = _find_settings_file()
    text = open(path, encoding="utf-8").read()
    if not text.startswith("---"):
        raise SystemExit(f"{path}: expected YAML frontmatter starting with ---")
    fm = text.split("---", 2)[1]
    return yaml.safe_load(fm) or {}


def local_dir(settings=None):
    s = settings or load_settings()
    base = s.get("local_dir")
    if not base:
        raise SystemExit("Set local_dir in .claude/drainer.local.md (folder with context.md + providers/).")
    return base
