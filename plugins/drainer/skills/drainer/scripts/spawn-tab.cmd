@echo off
REM spawn-tab.cmd - open ONE Windows Terminal tab running a fresh interactive Claude worker session.
REM Called from run-poller.py via:  subprocess.Popen(["cmd","/c", spawn-tab.cmd, TITLE, REPO, PROMPTFILE, MODEL, SUMMARYFILE])
REM A .cmd shim is used (not a direct Popen of wt.exe) because wt.exe tokenization breaks on quoted
REM paths passed through a Python subprocess; cmd escaping handles it reliably.
REM
REM   %1 TITLE        initial tab title (the worker's Claude session renames the tab itself once it starts)
REM   %2 REPO         starting directory (the drainer project)
REM   %3 PROMPTFILE   file holding the worker's full instructions (launch-session.ps1 -PromptFile)
REM   %4 MODEL        explicit model id for the worker (so it doesn't inherit the session default)
REM   %5 SUMMARYFILE  OPTIONAL file with a one-line item summary; launch-session.ps1 leads the seed with it
REM                   so the worker's Claude session names the tab descriptively. The digest spawns with
REM                   NO 5th arg.
set "TITLE=%~1"
set "REPO=%~2"
set "PFILE=%~3"
set "MODEL=%~4"
set "SFILE=%~5"
set "WT=%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"
set "LAUNCHER=%USERPROFILE%\OneDrive\Claude\scripts\launch-session.ps1"
REM -w drainer: always collect worker tabs in a single, consistently-named "drainer" window, rather
REM than -w 0 (most-recently-used), which is unpredictable when the scheduled task creates the window.
REM No --no-focus here: it governs only NEW-window creation, not a tab added to an existing window, so
REM it can't stop WT from activating the drainer window on each spawn (verified on WT 1.24). Worse, when
REM it precedes -w it makes WT 1.24 reject the whole command and swallow the tab. Focus is handled after
REM the spawn instead, by provider_base.spawn_tab restoring the prior foreground window.
REM No --suppressApplicationTitle: the worker's Claude session sets the tab title itself, which is what
REM shows its "needs attention" star when it yields to Russell. We steer that self-chosen title to be
REM descriptive by leading the seed with the item summary (launch-session.ps1 -SummaryFile).
REM
REM Only pass -SummaryFile when a 5th arg was actually given. An EMPTY "%SFILE%" gets eaten by wt's
REM tokenizer, leaving a dangling "-SummaryFile" with no value, which makes launch-session.ps1 fail with
REM "Missing an argument for parameter 'SummaryFile'". The digest spawns with no summary, so it must omit
REM the flag entirely rather than pass it empty.
if "%SFILE%"=="" (
  "%WT%" -w drainer new-tab --title "%TITLE%" --startingDirectory "%REPO%" powershell -NoExit -NoProfile -File "%LAUNCHER%" -PromptFile "%PFILE%" -Model "%MODEL%"
) else (
  "%WT%" -w drainer new-tab --title "%TITLE%" --startingDirectory "%REPO%" powershell -NoExit -NoProfile -File "%LAUNCHER%" -PromptFile "%PFILE%" -Model "%MODEL%" -SummaryFile "%SFILE%"
)
