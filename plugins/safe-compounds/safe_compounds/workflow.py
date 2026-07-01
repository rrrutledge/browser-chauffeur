"""Classify Workflow tool calls as auto-allowable.

A workflow is trusted by its declared name, not by tool name alone — spinning
up subagents is expensive and its safety depends entirely on which workflow
is running. The name comes either from a saved workflow (`tool_input.name`)
or, for an inline/dynamic script, from its required `meta.name` literal.
Only names the user has explicitly configured as blanket-trusted auto-allow;
everything else falls through to a manual prompt.
"""
import re

from . import config
from .log import log_debug

_META_NAME_RE = re.compile(r"meta\s*=\s*\{.*?\bname\s*:\s*['\"]([^'\"]+)['\"]", re.DOTALL)


def _declared_name(tool_input):
    name = tool_input.get('name')
    if name:
        return name
    script = tool_input.get('script') or ''
    m = _META_NAME_RE.search(script)
    return m.group(1) if m else None


def classify_workflow_tool(tool_input):
    """Return True to auto-allow a Workflow tool call, False to prompt."""
    name = _declared_name(tool_input)
    if not name:
        log_debug("Workflow: no declared name found, prompting")
        return False

    blanket = config.get_config().get('workflow_blanket_names', [])
    if name in blanket:
        log_debug(f"Workflow '{name}': blanket-approved (configured)")
        return True

    log_debug(f"Workflow '{name}': not in blanket list, prompting")
    return False
