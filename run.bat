@echo off
:: ---------------------------------------------------------------------------
:: run.bat — Launch the podcast generator (Windows)
:: Usage:
::   run.bat                          :: random topic
::   run.bat "Linux and security"     :: custom topic
::   run.bat --lang en "Open Source"  :: custom language + topic
:: ---------------------------------------------------------------------------
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
:: Remove trailing backslash
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
cd /d "%SCRIPT_DIR%"

:: ---------- Colors via ANSI (Windows 10+ supports VT sequences) ------------
:: Enable VT100 escape codes in cmd
for /f "tokens=*" %%A in ('ver') do set "_ver=%%A"
reg query HKCU\Console /v VirtualTerminalLevel >nul 2>&1 || (
    reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1
)

set "CYAN=[36m"
set "GREEN=[32m"
set "YELLOW=[33m"
set "RED=[31m"
set "NC=[0m"

goto :main

:log
echo %CYAN%[run]%NC% %*
exit /b 0

:ok
echo %GREEN%[ok]%NC%  %*
exit /b 0

:warn
echo %YELLOW%[warn]%NC% %*
exit /b 0

:err
echo %RED%[err]%NC%  %* 1>&2
exit /b 0

:: ---------- Main -----------------------------------------------------------
:main

:: ---------- Python ---------------------------------------------------------
set "PYTHON="
for %%C in (python3.exe python.exe) do (
    if "!PYTHON!"=="" (
        where %%C >nul 2>&1 && set "PYTHON=%%C"
    )
)

if "!PYTHON!"=="" (
    call :err "Python not found. Please install Python 3.9+ from https://python.org"
    exit /b 1
)

for /f "tokens=*" %%V in ('!PYTHON! -c "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")"') do set "PYTHON_VERSION=%%V"
call :log "Python detected: !PYTHON! (!PYTHON_VERSION!)"

:: ---------- Virtual environment --------------------------------------------
set "VENV_DIR=%SCRIPT_DIR%\.venv"

if not exist "!VENV_DIR!\" (
    call :log "Creating virtual environment..."
    !PYTHON! -m venv "!VENV_DIR!"
    if errorlevel 1 (
        call :err "Failed to create virtual environment."
        exit /b 1
    )
)

:: Activate the venv
set "PYTHON=!VENV_DIR!\Scripts\python.exe"
set "PIP=!VENV_DIR!\Scripts\pip.exe"

if not exist "!PYTHON!" (
    call :err "Virtual environment activation failed — python.exe not found in .venv\Scripts\"
    exit /b 1
)

:: ---------- Python dependencies --------------------------------------------
if exist "%SCRIPT_DIR%\requirements.txt" (
    call :log "Installing / verifying dependencies..."
    "!PIP!" install --quiet --upgrade pip
    "!PIP!" install --quiet -r "%SCRIPT_DIR%\requirements.txt"
    if errorlevel 1 (
        call :err "Failed to install dependencies."
        exit /b 1
    )
    call :ok "Dependencies OK"
) else (
    call :warn "requirements.txt not found, skipping installation."
)

:: ---------- Ollama check ---------------------------------------------------
where ollama.exe >nul 2>&1
if errorlevel 1 (
    call :warn "Ollama is not installed or not in PATH."
    call :warn "Install it from https://ollama.com, then run: ollama pull gemma3n"
)

:: ---------- Launch ---------------------------------------------------------
call :log "Starting podcast generator..."
echo.

:: Forward all arguments to main.py
"!PYTHON!" "%SCRIPT_DIR%\main.py" %*

endlocal
