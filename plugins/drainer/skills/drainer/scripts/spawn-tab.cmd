@echo off
REM spawn-tab.cmd - open ONE Windows Terminal tab running a fresh interactive Claude worker session.
REM Called from run-poller.py via:  subprocess.Popen(["cmd","/c", spawn-tab.cmd, TITLE, REPO, PROMPTFILE])
REM A .cmd shim is used (not a direct Popen of wt.exe) because wt.exe tokenization breaks on quoted
REM paths passed through a Python subprocess; cmd escaping handles it reliably.
REM
REM   %1 TITLE       tab title (e.g. drain:<id>)
REM   %2 REPO        starting directory (the drainer project)
REM   %3 PROMPTFILE  file holding the worker's full instructions (launch-session.ps1 -PromptFile)
REM   %4 MODEL       explicit model id for the worker (so it doesn't inherit the session default)
set "TITLE=%~1"
set "REPO=%~2"
set "PFILE=%~3"
set "MODEL=%~4"
set "WT=%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"
set "LAUNCHER=%USERPROFILE%\OneDrive\Claude\scripts\launch-session.ps1"
"%WT%" -w 0 new-tab --title "%TITLE%" --startingDirectory "%REPO%" powershell -NoExit -NoProfile -File "%LAUNCHER%" -PromptFile "%PFILE%" -Model "%MODEL%"
