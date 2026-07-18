param(
  [string]$Model,       # optional — when empty, no --model flag (inherit session default)
  [string]$PromptFile,  # drainer mode: full instructions live on disk; seed is a pointer
  [string]$SeedFile,    # handoff mode: file holding the literal seed text passed to claude
  [string]$SummaryFile, # optional (PromptFile mode): one-line item summary prepended to the seed so
                        #   Claude self-titles the tab descriptively (it names the session off its first
                        #   message). Prose-in-file per the rule below; only the path crosses the wt line.
  [string]$SessionId,   # optional explicit id; auto-generated in PromptFile mode
  [string]$Resume       # resume mode: session ID of an existing session to resume (no seed needed)
)
# Shared primitive: launch a fresh Claude session inside a Windows Terminal tab.
# This is the REAL launcher — the single copy — living inside the session-mgr
# plugin (the "session launcher" home; the resume-sessions skill uses it) so it
# ships version-pinned with the plugin. Reference THIS file:
#   - the handoff launcher, resume-sessions, and other cloud-file refs point at
#     this path directly (in the working clone).
#   - the drainer plugin ships a thin resolver (skills/drainer/scripts/launch-session.ps1,
#     run by spawn-tab.cmd via %~dp0) that finds the newest INSTALLED copy of this
#     file and forwards to it, so a worker is never launched from a floating
#     dev-clone branch. Keep that resolver's param block in sync with the one below
#     — a param not declared there is silently dropped instead of forwarded.
# Both callers route through here:
#   - drainer/spawn-tab.cmd  -> -PromptFile (browser loop; model = session default)
#   - the handoff launcher   -> -SeedFile -Model "claude-opus-4-8[1m]"
# Always invoked via `powershell -File` (NOT inline -Command): wt treats ';' as a tab
# delimiter and would truncate an inline command. `pwsh` is absent — use `powershell`.
# No startup beep on purpose — Claude Code's own notifications beep when it actually needs
# Russell (waiting for input / finished), the only time he wants a sound.
#
# CRITICAL — never pass free-text prose on the wt/powershell command line. An embedded `"`
# or `;` in a seed closes the quote early and wt re-tokenizes the leftover words as a
# program to launch (observed: "file not found"). So ALL prose arrives via a FILE
# (-PromptFile / -SeedFile); only paths, titles, model ids, and guids cross the wt line.
#
# Self-close: a session that wants to close its own tab reads $env:CLAUDE_HOST_PID, set by the
# user's PowerShell $PROFILE when the caller's `powershell` invocation loads it (both current
# callers do).
#
# When this script is itself invoked from a Bash tool call inside a running Claude Code session
# (every handoff/resume launched via that session's own Bash tool, as opposed to a plain shell),
# the OS process chain inherits that parent session's CLAUDE_CODE_CHILD_SESSION/CLAUDE_CODE_SESSION_ID/
# CLAUDE_PID env vars all the way down to the new `claude` process this script spawns. Claude Code
# reads CLAUDE_CODE_CHILD_SESSION on startup and suppresses its own transcript persistence for a
# process that thinks it's a child session — even though it's really a fresh, independent,
# human-driven session in its own tab. Confirmed in practice: a handoff session inherited these
# vars, ran for hours doing real work, and never wrote a single line to disk anywhere — its entire
# history existed only in process memory. Clear all three before ever invoking `claude` below so a
# newly spawned top-level session is never mistaken for a child of whatever launched it.
Remove-Item Env:\CLAUDE_CODE_CHILD_SESSION -ErrorAction SilentlyContinue
Remove-Item Env:\CLAUDE_CODE_SESSION_ID -ErrorAction SilentlyContinue
Remove-Item Env:\CLAUDE_PID -ErrorAction SilentlyContinue

# Ensures a session id exists and writes it to "<AnchorFile>.session" so peek.py (and anything else
# that wants to follow this tab's live transcript) can find it later — the two launch modes used to
# each carry their own copy of this, and only the -PromptFile copy actually ran, so a -SeedFile launch
# (every handoff) never got a receipt and could never be peeked at. One function, called from both
# branches below, so they can't drift out of sync again.
function Register-SessionReceipt {
  param(
    [Parameter(Mandatory)][string]$AnchorFile,
    [string]$SessionId
  )
  if (-not $SessionId) { $SessionId = [guid]::NewGuid().Guid }
  Set-Content -LiteralPath ($AnchorFile + ".session") -Value $SessionId -Encoding ascii
  Write-Host "launch-session id: $SessionId"
  return $SessionId
}

$seed = $null
if ($Resume) {
  $claudeArgs = @('--resume', $Resume)
  if ($Model) { $claudeArgs = @('--model', $Model) + $claudeArgs }
  # Own browser-chauffeur tabs for this resumed session (see note below).
  $env:BROWSER_CHAUFFEUR_OWNER_PID = $PID
  claude @claudeArgs
  return
}
if ($PromptFile) {
  if (-not (Test-Path -LiteralPath $PromptFile)) {
    Write-Host "launch-session: prompt file not found: $PromptFile" -ForegroundColor Red
    return
  }
  # Run with a fixed session id so the orchestrator can find this tab's full JSONL transcript later.
  $SessionId = Register-SessionReceipt -AnchorFile $PromptFile -SessionId $SessionId
  # Lead with a one-line item summary (if supplied) so Claude names the tab off it — a descriptive
  # title like "Handle Gmail security message" instead of "Review prompt-file instructions" — while the
  # attention star still works (no --suppressApplicationTitle). Then point it at the full instructions.
  # Keep the seed ONE line (the proven-safe format — the original seed was single-line and unbroken).
  # A space-join (not a newline) plus a quote-free summary avoids PowerShell 5.1 mangling the seed when it
  # hands it to `claude`: an embedded newline or double quote truncates the arg and drops the read-the-file
  # pointer, leaving the worker with no idea what item it's on.
  # Resilient by design: the summary is a NICETY (a descriptive tab title), never required. Whatever we
  # get — no file, missing file, empty file, or an unreadable one — we just skip the lead and move on with
  # the plain pointer. Any failure reading it must never block the worker from launching.
  $lead = ''
  try {
    if ($SummaryFile -and (Test-Path -LiteralPath $SummaryFile)) {
      $lead = (Get-Content -Raw -Encoding utf8 -LiteralPath $SummaryFile -ErrorAction Stop).Trim() -replace '\s+', ' '
      if ($lead) { $lead = $lead + " " }
    }
  } catch { $lead = '' }
  $seed = $lead + "Your task instructions are in '$PromptFile' - open it and begin immediately without waiting for further input."
}
elseif ($SeedFile) {
  if (-not (Test-Path -LiteralPath $SeedFile)) {
    Write-Host "launch-session: seed file not found: $SeedFile" -ForegroundColor Red
    return
  }
  # Same receipt as the -PromptFile branch above, so a handoff can be peeked at too — this previously
  # only fired when a caller happened to pass -SessionId explicitly, which none do.
  $SessionId = Register-SessionReceipt -AnchorFile $SeedFile -SessionId $SessionId
  $seed = (Get-Content -Raw -LiteralPath $SeedFile).Trim()
}
else {
  Write-Host "launch-session: supply -PromptFile, -SeedFile, or -Resume <session-id>" -ForegroundColor Red
  return
}

$claudeArgs = @()
if ($Model)     { $claudeArgs += @('--model', $Model) }
if ($SessionId) { $claudeArgs += @('--session-id', $SessionId) }
$claudeArgs += $seed
# Own any browser-chauffeur tabs this session opens. The browser-chauffeur sweep
# keeps a tab alive while its owner process is running and reclaims it when the
# owner is gone, so tying ownership to THIS host process (which lives exactly as
# long as this WT tab) means the browser tab is cleaned up when the tab closes —
# not orphaned. Every node script the session spawns inherits these env vars.
$env:BROWSER_CHAUFFEUR_OWNER_PID = $PID
claude @claudeArgs
