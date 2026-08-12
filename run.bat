@echo off
setlocal EnableExtensions
rem ============================================================
rem saipenview launcher -- robust + silent + verifiable.
rem  1) venv is guaranteed to exist: bootstrapped if missing, with
rem     best-effort python discovery (py -3 -> python) and every
rem     step logged instead of dying silently.
rem  2) app launches with cwd = project root, so `-m saipenview`
rem     resolves even if the package was never pip-installed.
rem  3) a Start-Process PID is polled for 5 seconds: a crash right
rem     after launch is detected and the bat exits non-zero so the
rem     caller can react.
rem Log: %LOCALAPPDATA%\saipenview\launch.log
rem ============================================================

set "ROOT=%~dp0"
set "PYW=%ROOT%.venv\Scripts\pythonw.exe"
set "LOGDIR=%LOCALAPPDATA%\saipenview"
set "LOG=%LOGDIR%\launch.log"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>nul

echo %date% %time% [launch] saipenview start >>"%LOG%"

if not exist "%PYW%" goto :bootstrap
goto :launch

:bootstrap
echo %date% %time% [bootstrap] venv missing -- creating >>"%LOG%"
set "BOOTPY="
where py >nul 2>nul
if not errorlevel 1 set "BOOTPY=py -3"
if not defined BOOTPY (
    where python >nul 2>nul
    if not errorlevel 1 set "BOOTPY=python"
)
if not defined BOOTPY (
    echo %date% %time% [bootstrap] FATAL: no python found (py -3 / python) >>"%LOG%"
    exit /b 1
)
%BOOTPY% -m venv "%ROOT%.venv" >>"%LOG%" 2>&1
if errorlevel 1 (
    echo %date% %time% [bootstrap] FATAL: venv creation failed >>"%LOG%"
    exit /b 1
)
"%PYW%" -m pip install --disable-pip-version-check -q -r "%ROOT%requirements.txt" >>"%LOG%" 2>&1
if errorlevel 1 (
    echo %date% %time% [bootstrap] FATAL: pip install failed >>"%LOG%"
    exit /b 1
)
echo %date% %time% [bootstrap] venv ready >>"%LOG%"

:launch
rem App has a single-instance guard: a second process hands the first a SHOW
rem request and exits 0. So BOTH outcomes below are success:
rem   alive after 5s  -> fresh instance is running
rem   exited with 0   -> existing instance was woken, its window is showing
rem Only a non-zero exit means the app really failed to start.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $p = Start-Process -FilePath $env:PYW -ArgumentList @('-m','saipenview') -WorkingDirectory $env:ROOT -PassThru; Start-Sleep -Seconds 5; if ($p.HasExited) { if ($p.ExitCode -eq 0) { Write-Output 'exited 0 (single-instance show requested)'; exit 0 }; Write-Output ('exit code ' + $p.ExitCode); exit 1 }; Write-Output 'alive after 5s'; exit 0" >>"%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" (
    echo %date% %time% [launch] ok >>"%LOG%"
    exit /b 0
)
echo %date% %time% [launch] FAILED: pythonw exited non-zero within 5s >>"%LOG%"
exit /b 1
