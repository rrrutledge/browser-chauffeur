"""Shared reader for `.claude/drainer.local.md` — the per-machine drainer settings.

Both entry points use it: the fast-loop poller (`run-poller.py`) and the once-a-day digest
launcher (`run-digest.py`). Keeping the parse in one place means the two never drift on knob
names or defaults. Everything here is deterministic string/int parsing of the YAML frontmatter;
no source mechanics live here.
"""
import os
import re


def _read_local(repo):
    path = os.path.join(repo, ".claude", "drainer.local.md")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def parse_provider_names(text):
    """The immediate child keys under the `providers:` block (e.g. outlook-graph, trello)."""
    names, in_block = [], False
    for line in text.splitlines():
        if re.match(r"^\s*providers\s*:\s*$", line):
            in_block = True
            continue
        if in_block:
            if re.match(r"^\S", line) or line.strip() in ("---", ""):
                if line.strip() == "":
                    continue
                if re.match(r"^\S", line):
                    break
            m = re.match(r"^\s{2}([A-Za-z0-9_-]+)\s*:", line)
            if m:
                names.append(m.group(1))
    return names


def read_config(repo):
    """Pull the scalar knobs + enabled provider names out of .claude/drainer.local.md frontmatter."""
    text = _read_local(repo)

    def scalar(key, default):
        m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*$", text, re.MULTILINE)
        return m.group(1).strip().strip('"\'') if m else default

    runtime_dir = scalar("runtime_dir", ".tmp/drainer")
    if not os.path.isabs(runtime_dir):
        runtime_dir = os.path.join(repo, runtime_dir)
    return {
        "providers": parse_provider_names(text),
        "repo": repo,  # so adapters that drain configured targets (e.g. trello boards) can re-read this file
        "runtime_dir": runtime_dir,
        "local_dir": scalar("local_dir", os.path.join(repo, "drainer-local")),
        "max_open_tabs": int(scalar("max_open_tabs", "3")),
        "max_messages_per_cycle": int(scalar("max_messages_per_cycle", "50")),
        "idle_threshold_seconds": int(scalar("idle_threshold_seconds", "600")),
        # Worker tabs need an explicit model — otherwise they inherit the session default, which may be
        # a 1M-context model the account can't use. The poller picks per item by triage complexity:
        # simple -> worker_model, complex -> worker_model_complex (both standard context).
        "worker_model": scalar("worker_model", "claude-sonnet-5"),
        "worker_model_complex": scalar("worker_model_complex", "claude-opus-4-8"),
        # The triage call must also pin a model — under the scheduled task it has no parent session,
        # so it would otherwise inherit a 1M-context default the account can't use. Standard Sonnet.
        "triage_model": scalar("triage_model", "claude-sonnet-5"),
        # The once-a-day digest session. It summarizes fyi, groups junk with source-stop proposals,
        # and runs the reconciliation scan — judgment-heavy, so a stronger standard-context model.
        "digest_model": scalar("digest_model", "claude-opus-4-8"),
        # Digest-only informational threshold: the EOD digest lists any needs-you item still
        # dispatched-but-uncleared past this many hours. The poller's own orphan recovery is purely
        # liveness-based (a closed worker tab, detected via its session process) and uses no timeout.
        "stale_hours": int(scalar("stale_hours", "12")),
        # Orphan-recovery grace: a worker tab whose claude --session-id process is gone is treated as
        # closed and recovered, but only once it's been launched at least this many minutes — so a
        # just-dispatched tab whose process hasn't appeared yet isn't misread as dead.
        "orphan_grace_minutes": int(scalar("orphan_grace_minutes", "15")),
        # Wall-clock time (HH:MM, 24h) the daily digest task fires; consumed by the installer.
        "digest_time": scalar("digest_time", "17:00"),
    }


def provider_search_dirs(plugin_providers_dir, local_dir):
    """Where a provider's files are looked up, in order: the plugin's own `providers/`, then the
    machine-local `<local_dir>/providers/`. The plugin ships the generic, identity-free providers; a
    machine keeps work- or personal-specific providers (that shouldn't live in the shared plugin) in
    `<local_dir>/providers/` and enables them by name in drainer.local.md exactly like a shipped one."""
    dirs = [plugin_providers_dir]
    if local_dir:
        dirs.append(os.path.join(local_dir, "providers"))
    return dirs


def find_provider_file(plugin_providers_dir, local_dir, name, suffix):
    """Resolve `<name><suffix>` (e.g. `-adapter.py` / `-provider.md`) across the search dirs above.
    Returns the first existing path, or None if no dir has it."""
    for d in provider_search_dirs(plugin_providers_dir, local_dir):
        path = os.path.join(d, f"{name}{suffix}")
        if os.path.exists(path):
            return path
    return None
