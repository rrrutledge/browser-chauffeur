"""Consumer configuration.

The plugin ships with no organization-specific data. A consumer supplies their
own trusted domains, MCP servers, commands, and script directories via a
machine-local JSON file (default ~/.claude/safe-compounds-config.json, or the
path in SAFE_COMPOUNDS_CONFIG_JSON).

Example ~/.claude/safe-compounds-config.json:
    {
      "trusted_commands": ["mycli"],
      "curl_domains": ["atlassian.net", "mycorp.sharepoint.com"],
      "mcp_blanket_servers": ["plugin_product-management_atlassian"],
      "trusted_script_dirs": ["my-plugins/"],
      "learned_sync_exclude": ["my-internal-cli"],
      "workflow_blanket_names": ["code-review"]
    }

Every value here is a command *name* or path/domain string — a name-level
allowlist, not a safety verdict. (The hook decides "safe" per command at
runtime; this file just feeds the lists those decisions draw on.)

All keys are optional; defaults are empty, which means "trust nothing extra"
(curl is then limited to localhost and read-only GETs, no MCP server is
blanket-allowed, etc.).

`trusted_commands` is your private/company trust — it is never promoted to the
shared PR. `learned_sync_exclude` blocklists additional command names that the
AI might learn but should never be shared publicly (e.g. an internal tool name).

`workflow_blanket_names` auto-allows Workflow tool calls by their declared
`meta.name` — matched whether the workflow was launched by saved name or as
an inline/dynamic script. Everything not listed still prompts, since a
workflow can spin up many subagents.
"""
import json
import os

_DEFAULTS = {
    "trusted_commands": [],
    "curl_domains": [],
    "mcp_blanket_servers": [],
    "trusted_script_dirs": [],
    "learned_sync_exclude": [],
    "workflow_blanket_names": [],
}

_CONFIG = None


def _path():
    return os.environ.get(
        'SAFE_COMPOUNDS_CONFIG_JSON',
        os.path.expanduser('~/.claude/safe-compounds-config.json'),
    )


def get_config():
    """Return the merged config dict (cached for this process)."""
    global _CONFIG
    if _CONFIG is None:
        data = dict(_DEFAULTS)
        try:
            with open(_path(), encoding='utf-8') as f:
                loaded = json.load(f)
            for key in _DEFAULTS:
                if key in loaded:
                    data[key] = loaded[key]
        except Exception:
            pass
        _CONFIG = data
    return _CONFIG


def reset():
    """Clear the cached config (used by tests)."""
    global _CONFIG
    _CONFIG = None
