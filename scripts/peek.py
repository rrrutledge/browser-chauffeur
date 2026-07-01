"""Peek at a spawned Claude session's transcript as a compact timeline.

Usage:
  python peek.py <session-id-or-.session-file-or-jsonl-path> [--tail N]

Claude records every session as JSONL under ~/.claude/projects/<proj>/<session-id>.jsonl.
This prints a readable timeline (assistant text, tool calls + short results), skipping the
big base64 image blobs, so an orchestrator can monitor how a launched session is doing.
"""
import json
import os
import sys
import glob

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECTS = os.path.expanduser("~/.claude/projects")


def resolve_jsonl(arg):
    if arg.endswith(".jsonl") and os.path.exists(arg):
        return arg
    if arg.endswith(".session") and os.path.exists(arg):
        with open(arg, encoding="utf-8") as f:
            arg = f.read().strip()
    # now arg should be a session id. A spawned session can leave a tiny ai-title
    # stub under one project dir while the real conversation lands under another
    # (e.g. a git worktree vs its main repo). Pick the LARGEST match — the stub is
    # ~120 bytes; the real transcript is the big one.
    hits = glob.glob(os.path.join(PROJECTS, "**", arg + ".jsonl"), recursive=True)
    if not hits:
        return None
    return max(hits, key=lambda p: os.path.getsize(p))


def short(s, n=200):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "..."


def text_from_content(content):
    """Pull human-readable text + tool calls from a message content (list or str)."""
    out = []
    if isinstance(content, str):
        return [("text", content)]
    if isinstance(content, list):
        for blk in content:
            if not isinstance(blk, dict):
                continue
            t = blk.get("type")
            if t == "text":
                out.append(("text", blk.get("text", "")))
            elif t == "thinking":
                out.append(("think", blk.get("thinking", "")))
            elif t == "tool_use":
                name = blk.get("name", "tool")
                inp = blk.get("input", {})
                # keep tool input compact; never dump base64
                desc = inp.get("command") or inp.get("description") or inp.get("file_path") \
                    or inp.get("prompt") or inp.get("skill") or ""
                out.append(("tool", f"{name}({short(desc, 120)})"))
            elif t == "tool_result":
                c = blk.get("content", "")
                if isinstance(c, list):
                    c = " ".join(b.get("text", "[non-text]") for b in c if isinstance(b, dict))
                out.append(("result", short(c, 160)))
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    tail = None
    if "--tail" in sys.argv:
        i = sys.argv.index("--tail")
        tail = int(sys.argv[i + 1])
    jsonl = resolve_jsonl(sys.argv[1])
    if not jsonl:
        print(f"No transcript found for {sys.argv[1]!r}")
        return 1
    print(f"# {jsonl}\n")
    rows = []
    with open(jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            msg = rec.get("message") or {}
            role = rec.get("type") or msg.get("role") or "?"
            content = msg.get("content", rec.get("content", ""))
            for kind, val in text_from_content(content):
                val = short(val, 300)
                if not val.strip():
                    continue
                tag = {"text": role, "think": "(thinking)", "tool": ">> tool",
                       "result": "   ="}.get(kind, kind)
                rows.append(f"{tag}: {val}")
    if tail:
        rows = rows[-tail:]
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
