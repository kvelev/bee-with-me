@echo off
rem One-click start for Windows: double-click this file (or a shortcut to it).
rem Runs start.ps1 from the folder this file is in. On an error the window stays open so the
rem message can be read or photographed, and the exit code of start.ps1 is kept.
rem PowerShell by full path: cmd.exe looks in the current folder before PATH.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "rc=%errorlevel%"
if not "%rc%"=="0" pause
exit /b %rc%
