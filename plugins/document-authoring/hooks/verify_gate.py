#!/usr/bin/env python3
"""writing-review gate - makes the drafting loop's Verify step contractual.

A draft cannot be staged until a fresh writing-review pass has run against that exact
draft content. The review flow proves it ran by minting a receipt keyed to a hash of the
body file; this hook, on a stage command, recomputes that hash and blocks unless a fresh
receipt exists.

Three modes in one file (single source of truth for the hash + receipt layout, so the
minting side and the gating side can never drift apart):

  * hook mode  - no args, reads a PreToolUse payload on stdin. Vetoes (deny) a stage
                 command whose body file has no fresh receipt; defers otherwise.
  * mint <f>   - the review flow's final step: hash body file <f>, write its receipt.
  * check <f>  - exit 0 if <f> has a fresh receipt (or is a pure reaction), else exit 1.
                 For surfaces the hook can't see (Teams/Slack composers), where the flow
                 asserts the receipt itself rather than a stage command triggering the gate.

Why the binding is exact: every gated stage command passes the draft body in a FILE
(gmail.js / mail.js use --body-file=<p>; ms-rest outlook-mail.js uses --json <p>). The
reviewer reviews that file, the flow mints on that file, the stage command consumes that
file - so hashing the file's content matches on both sides with no per-format
normalization. Edit the draft and the hash changes, so a stale review can't satisfy the
gate. The receipt attests that a review ran, not that it was clean - the writer's
standing-to-disagree is preserved; this enforces process, not verdict.

The hook is a pure veto: it only ever denies or defers, never approves, so it composes
with safe-compounds without granting anything. On any internal error it defers (fail-open)
- it must never be the mysterious reason a legitimate stage fails; its job is catching the
common case of no review at all, and the deny message always spells out the fix.
"""

import sys
import os
import re
import json
import time
import shlex
import hashlib
import datetime

RECEIPT_DIR = os.environ.get("WRITING_REVIEW_RECEIPT_DIR") or os.path.expanduser(
    "~/.claude/writing-review/receipts"
)
TTL_SECONDS = 24 * 3600

# Known stage commands, keyed by script basename. A command is a stage command when it
# names one of these scripts, carries one of its compose verbs, and supplies its body flag.
# Send-of-a-staged-draft (gmail --send-draft, outlook-mail send-draft) carries no body and
# is intentionally absent - that draft was already gated at stage time, and the send is
# Russell's explicit act. ms-graph --send-self composes fresh into a body file, so it is
# gated like a stage.
STAGE_SCRIPTS = {
    "gmail.js": {"verbs": {"--reply", "--draft-new"}, "body_flag": "--body-file"},
    "mail.js": {"verbs": {"--reply", "--draft-new", "--send-self"}, "body_flag": "--body-file"},
    "outlook-mail.js": {"verbs": {"create-draft", "create-reply"}, "body_flag": "--json"},
}

# Native Gmail connector compose/send verbs. Staging Russell's mail this way bypasses both
# this gate and the gmail skill's signature/threading handling, so it is denied outright
# with a redirect. Read-only Gmail verbs (search/get/list/label/...) are untouched.
GMAIL_MCP_WRITE = {
    "mcp__claude_ai_Gmail__create_draft",
    "mcp__claude_ai_Gmail__update_draft",
    "mcp__claude_ai_Gmail__reply",
    "mcp__claude_ai_Gmail__forward",
    "mcp__claude_ai_Gmail__send_message",
}


# --- shared hash + receipt layout (used identically by hook, mint, and check) ---

def normalized_text(path):
    """Read a body file as the canonical text both sides hash. Line endings are unified
    and surrounding whitespace trimmed so a stray CRLF or trailing newline can't split a
    genuine match; nothing else is altered, so any prose change moves the hash."""
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def has_prose(text):
    """A body with no alphabetic character is a pure emoji/symbol reaction (a bare 👍),
    which has no prose to review and is exempt from the gate."""
    return re.search(r"[A-Za-z]", text) is not None


def receipt_path(h):
    return os.path.join(RECEIPT_DIR, h + ".json")


def has_fresh_receipt(h):
    path = receipt_path(h)
    if not os.path.isfile(path):
        return False
    return (time.time() - os.path.getmtime(path)) <= TTL_SECONDS


# --- command parsing ---

def find_body_file(command):
    """Return the body-file path if `command` is a recognized stage command, else None.

    Two shapes count as a stage command. A named mail script (gmail.js / mail.js /
    outlook-mail.js) carrying its compose verb and body flag is one. A browser-chauffeur
    composer run is the other: a `--cdp-port` browser session that declares the message it
    will type via `--body-file`. The Slack and Teams composers type into a web page rather
    than into a script argument, so message-draft routes their body through a declared file,
    which is what lets this gate reach them the same way it reaches mail. A browser-chauffeur
    run that carries no `--body-file` (a screenshot, a scrape) is not a stage command and
    passes straight through."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    for i, tok in enumerate(tokens):
        base = tok.replace("\\", "/").rsplit("/", 1)[-1]
        spec = STAGE_SCRIPTS.get(base)
        if not spec:
            continue
        rest = tokens[i + 1:]
        if not any(v in rest for v in spec["verbs"]):
            continue
        path = extract_flag_value(rest, spec["body_flag"])
        if path:
            return path
    if any(t == "--cdp-port" or t.startswith("--cdp-port=") for t in tokens):
        path = extract_flag_value(tokens, "--body-file")
        if path:
            return path
    return None


def extract_flag_value(tokens, flag):
    """Read a flag value in either `--flag=value` or `--flag value` form."""
    prefix = flag + "="
    for j, tok in enumerate(tokens):
        if tok == flag and j + 1 < len(tokens):
            return tokens[j + 1]
        if tok.startswith(prefix):
            return tok[len(prefix):]
    return None


# --- hook decision output (the PreToolUse contract) ---

def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def defer():
    sys.exit(0)


def stage_block_reason(body_path, h):
    return (
        "Blocked: staging this draft needs a fresh writing-review pass first.\n"
        f"The body file {body_path} has no review receipt (content {h[:12]}...).\n"
        "Do this, then re-run the stage command unchanged:\n"
        "  1. Dispatch the writing-review skill on this exact body file - a fresh "
        "subagent that did not write the draft, per the drafting loop's Verify step.\n"
        "  2. When the review loop converges, mint the receipt:\n"
        f'     python "{os.path.abspath(__file__)}" mint "{body_path}"\n'
        "The receipt binds to the file's content, so any later edit needs a fresh review "
        "and mint. A pure emoji/reaction body (no letters) never reaches this gate."
    )


MCP_REDIRECT_REASON = (
    "Blocked: staging or sending Russell's mail through the native Gmail connector bypasses "
    "the writing-review gate and the gmail skill's signature/threading handling. Stage "
    "through the gmail skill's gmail.js instead: write the body to a file, dispatch "
    "writing-review on it, mint a receipt, then "
    "`node <gmail.js> --reply --message-id=<id> --body-file=<file>` (or --draft-new). "
    "Read-only Gmail lookups (search/get/list) stay fine through the connector."
)


def run_hook():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = data.get("tool_name", "") or ""
    tool_input = data.get("tool_input", {}) or {}
    try:
        if tool == "Bash":
            body_path = find_body_file(tool_input.get("command", "") or "")
            if not body_path:
                defer()
            if not os.path.isabs(body_path):
                body_path = os.path.join(os.getcwd(), body_path)
            if not os.path.isfile(body_path):
                defer()
            text = normalized_text(body_path)
            if not has_prose(text):
                defer()
            h = content_hash(text)
            if has_fresh_receipt(h):
                defer()
            deny(stage_block_reason(body_path, h))
        elif tool.startswith("mcp__"):
            if tool in GMAIL_MCP_WRITE:
                deny(MCP_REDIRECT_REASON)
            defer()
        else:
            defer()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)


# --- mint / check subcommands ---

def cmd_mint(path, verdict):
    if not path or not os.path.isfile(path):
        print(f"mint: body file not found: {path}", file=sys.stderr)
        return 2
    text = normalized_text(path)
    h = content_hash(text)
    os.makedirs(RECEIPT_DIR, exist_ok=True)
    receipt = {
        "sha256": h,
        "source_file": os.path.abspath(path),
        "created_at": datetime.datetime.now().astimezone().isoformat(),
        "verdict": verdict or "reviewed",
        "chars": len(text),
    }
    with open(receipt_path(h), "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2)
    print(f"writing-review receipt minted: {h[:12]}... for {path}")
    return 0


def cmd_check(path):
    if not path or not os.path.isfile(path):
        print(f"check: body file not found: {path}", file=sys.stderr)
        return 2
    text = normalized_text(path)
    if not has_prose(text):
        print("check: no prose (pure reaction) - no receipt required")
        return 0
    h = content_hash(text)
    if has_fresh_receipt(h):
        print(f"check: OK - fresh receipt for {h[:12]}...")
        return 0
    print(
        f"check: NO fresh receipt for {path} (content {h[:12]}...). "
        "Dispatch writing-review on this file, then mint.",
        file=sys.stderr,
    )
    return 1


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "mint":
        verdict = None
        rest = argv[1:]
        if "--verdict" in rest:
            i = rest.index("--verdict")
            verdict = rest[i + 1] if i + 1 < len(rest) else None
            rest = rest[:i] + rest[i + 2:]
        sys.exit(cmd_mint(rest[0] if rest else None, verdict))
    if argv and argv[0] == "check":
        sys.exit(cmd_check(argv[1] if len(argv) > 1 else None))
    run_hook()


if __name__ == "__main__":
    main()
