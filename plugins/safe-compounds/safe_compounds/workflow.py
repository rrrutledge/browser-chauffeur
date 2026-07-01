"""Classify Workflow tool calls as auto-allowable.

Only a *saved* workflow (`tool_input.name` referencing a fixed, previously
authored script — built-in or from `.claude/workflows/`) can be blanket
-trusted, the same way `trusted_script_dirs` trusts a directory's contents
rather than re-inspecting every run. An inline/dynamic `script` payload is
arbitrary text supplied with the call itself, so nothing in it — including a
self-declared `meta.name` — is proof of what the script actually does; it
always falls through to a manual prompt, regardless of what name it claims.
"""
from . import config
from .log import log_debug


def classify_workflow_tool(tool_input):
    """Return True to auto-allow a Workflow tool call, False to prompt."""
    name = tool_input.get('name')
    if not name:
        log_debug("Workflow: no saved workflow name (inline script or missing), prompting")
        return False

    blanket = config.get_config().get('workflow_blanket_names', [])
    if name in blanket:
        log_debug(f"Workflow '{name}': blanket-approved (configured)")
        return True

    log_debug(f"Workflow '{name}': not in blanket list, prompting")
    return False
