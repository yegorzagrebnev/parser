@echo off
@chcp 65001 >nul

setlocal

set REQUIRED_MAJOR=3
set REQUIRED_MINOR=13
set REQUIRED_PATCH=5
set PY_EXE=python
set VENV_DIR=venv
set REQUIREMENTS=requirements.txt
set APP_FILE=app.py
set PY_INSTALLER_URL=https://www.python.org/ftp/python/3.13.5/python-3.13.5-amd64.exe
set PY_INSTALLER=python-3.13.5-amd64.exe

echo Checking for installed Python...

%PY_EXE% --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Starting installation...
    goto :install_python
)

for /f "tokens=2 delims= " %%v in ('%PY_EXE% --version') do set CURRENT_VER=%%v
for /f "tokens=1,2,3 delims=." %%a in ("%CURRENT_VER%") do (
    set MAJOR=%%a
    set MINOR=%%b
    set PATCH=%%c
)

if %MAJOR% LSS %REQUIRED_MAJOR% (
    echo Installed Python version is too old: %CURRENT_VER%
    goto :install_python
)
if %MAJOR%==%REQUIRED_MAJOR% if %MINOR% LSS %REQUIRED_MINOR% (
    echo Installed Python version is too old: %CURRENT_VER%
    goto :install_python
)

echo Found Python %CURRENT_VER%

goto :setup_venv

:install_python
echo Downloading Python %REQUIRED_MAJOR%.%REQUIRED_MINOR%.%REQUIRED_PATCH%...
curl -L -o %PY_INSTALLER% %PY_INSTALLER_URL%
if errorlevel 1 (
    echo [ERROR] Failed to download Python installer.
    pause
    exit /b 1
)

echo Installing Python...
start /wait "" "%PY_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
if errorlevel 1 (
    echo [ERROR] Failed to install Python.
    pause
    exit /b 1
)

set PY_EXE=python

:setup_venv
if not exist %VENV_DIR% (
    echo Creating virtual environment...
    %PY_EXE% -m venv %VENV_DIR%
)

echo Installing dependencies...
%VENV_DIR%\Scripts\python -m pip install --upgrade pip
%VENV_DIR%\Scripts\python -m pip install -r %REQUIREMENTS%

echo Launching Streamlit application...
%VENV_DIR%\Scripts\python -m streamlit run %APP_FILE%

endlocal
pause
