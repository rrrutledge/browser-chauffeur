"""Classify MCP tool calls (mcp__<server>__<operation>) as auto-allowable.

Whole servers can be blanket-allowed; otherwise the operation's leading verb
decides: read-only and reversible-write verbs allow, destructive or
unrecognized verbs fall through to a manual prompt.
"""
import re

from . import config
from .log import log_debug

MCP_READONLY_VERBS = (
    'get', 'list', 'search', 'fetch', 'read', 'view', 'describe', 'query',
    'lookup', 'find', 'show', 'check', 'browse', 'preview', 'inspect',
    'count', 'download', 'status',
)
MCP_REVERSIBLE_WRITE_VERBS = (
    'create', 'add', 'update', 'edit', 'comment', 'transition', 'link',
    'set', 'put', 'post', 'append', 'rename', 'move', 'assign', 'label',
    'tag', 'upsert', 'write', 'attach', 'star', 'watch', 'subscribe', 'copy',
)
MCP_DESTRUCTIVE_VERBS = (
    'delete', 'remove', 'purge', 'drop', 'destroy', 'trash', 'erase',
    'wipe', 'revoke', 'deactivate', 'disable', 'uninstall', 'unlink',
    'unassign', 'clear', 'reset', 'authenticate', 'authorize',
)


def classify_mcp_tool(tool_name):
    """Return True to auto-allow an MCP tool call, False to prompt."""
    parts = tool_name.split('__')
    server = parts[1] if len(parts) > 1 else ''
    operation = parts[-1] if len(parts) > 2 else ''

    if tool_name in config.get_config().get('mcp_blanket_tools', []):
        log_debug(f"MCP {tool_name}: tool blanket-approved (configured)")
        return True

    if server in config.get_config().get('mcp_blanket_servers', []):
        log_debug(f"MCP {tool_name}: server blanket-approved (configured)")
        return True

    name = operation.lower()
    verb_match = re.match(r'[a-z]+', name)
    verb = verb_match.group(0) if verb_match else name

    if verb in MCP_DESTRUCTIVE_VERBS or any(name.startswith(v) for v in MCP_DESTRUCTIVE_VERBS):
        log_debug(f"MCP {tool_name}: destructive verb '{verb}', prompting")
        return False
    if verb in MCP_READONLY_VERBS or any(name.startswith(v) for v in MCP_READONLY_VERBS):
        log_debug(f"MCP {tool_name}: read-only verb '{verb}', approving")
        return True
    if verb in MCP_REVERSIBLE_WRITE_VERBS or any(name.startswith(v) for v in MCP_REVERSIBLE_WRITE_VERBS):
        log_debug(f"MCP {tool_name}: reversible-write verb '{verb}', approving")
        return True

    log_debug(f"MCP {tool_name}: unrecognized verb '{verb}', prompting")
    return False
