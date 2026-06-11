"""Classify MCP tool calls (mcp__<server>__<operation>) as auto-approvable.

Whole servers can be blanket-approved; otherwise the operation's leading verb
decides: read-only and reversible-write verbs approve, destructive or
unrecognized verbs fall through to a manual prompt.
"""
import re

from .log import log_debug

MCP_BLANKET_APPROVE_SERVERS = (
    'plugin_product-management_atlassian',
    'plugin_architect_atlassian',
)
MCP_READONLY_VERBS = (
    'get', 'list', 'search', 'fetch', 'read', 'view', 'describe', 'query',
    'lookup', 'find', 'show', 'check', 'browse', 'preview', 'inspect',
    'count', 'download', 'status',
)
MCP_REVERSIBLE_WRITE_VERBS = (
    'create', 'add', 'update', 'edit', 'comment', 'transition', 'link',
    'set', 'put', 'post', 'append', 'rename', 'move', 'assign', 'label',
    'tag', 'upsert', 'write', 'attach', 'star', 'watch', 'subscribe',
)
MCP_DESTRUCTIVE_VERBS = (
    'delete', 'remove', 'purge', 'drop', 'destroy', 'trash', 'erase',
    'wipe', 'revoke', 'deactivate', 'disable', 'uninstall', 'unlink',
    'unassign', 'clear', 'reset', 'authenticate', 'authorize',
)


def classify_mcp_tool(tool_name):
    """Return True to auto-approve an MCP tool call, False to prompt."""
    parts = tool_name.split('__')
    server = parts[1] if len(parts) > 1 else ''
    operation = parts[-1] if len(parts) > 2 else ''

    if server in MCP_BLANKET_APPROVE_SERVERS:
        log_debug(f"MCP {tool_name}: server blanket-approved")
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
