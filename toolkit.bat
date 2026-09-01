@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

rem ===========================================================================
rem  toolkit.bat  —  P3CC's command file
rem ===========================================================================
rem  Double-click it for a menu, or call it with a command:
rem
rem      toolkit setup      create .venv and install everything
rem      toolkit run        start the GUI (app.py)
rem      toolkit test       run the pytest suite (tests/)
rem      toolkit check      what this machine can and cannot run
rem      toolkit package    build the portable P3CC.exe + zip it
rem
rem  Everything runs from the folder this file sits in, so it works wherever
rem  the project is copied to. If .venv exists its Python is used; otherwise
rem  the system Python is, so the file still works before setup has been run.
rem ===========================================================================

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if exist "%VENV_PY%" (
    set "PY=%VENV_PY%"
) else (
    set "PY=python"
)

if "%~1"=="" goto menu
set "ACTION=%~1"
goto dispatch

:menu
echo.
echo   P3CC Toolkit
echo   ------------
echo     1  Run the program
echo     2  Run the tests
echo     3  Check this machine
echo     4  Set up (create .venv, install packages)
echo     5  Build the portable zip
echo     0  Exit
echo.
set "CHOICE="
set /p "CHOICE=Choose: "
if "%CHOICE%"=="1" set "ACTION=run"
if "%CHOICE%"=="2" set "ACTION=test"
if "%CHOICE%"=="3" set "ACTION=check"
if "%CHOICE%"=="4" set "ACTION=setup"
if "%CHOICE%"=="5" set "ACTION=package"
if "%CHOICE%"=="0" goto end
if not defined ACTION goto menu

:dispatch
if /i "%ACTION%"=="setup"   goto setup
if /i "%ACTION%"=="run"     goto run
if /i "%ACTION%"=="test"    goto test
if /i "%ACTION%"=="check"   goto check
if /i "%ACTION%"=="package" goto package
echo Unknown command: %ACTION%
echo Use: setup ^| run ^| test ^| check ^| package
set "EXITCODE=2"
goto end

rem ---------------------------------------------------------------------------
:setup
echo Creating the virtual environment...
if not exist "%VENV_PY%" (
    python -m venv .venv
    if errorlevel 1 (
        echo Could not create .venv. Is Python installed and on PATH?
        set "EXITCODE=1"
        goto end
    )
)
echo Installing packages from requirements-dev.txt (runtime deps + pyinstaller)...
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip
"%~dp0.venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 (
    echo Installing the packages failed. See the messages above.
    set "EXITCODE=1"
    goto end
)
echo.
echo Setup finished. Checking what the machine can run:
"%~dp0.venv\Scripts\python.exe" -c "import sys,platform,importlib.util as u; print('Python  :', sys.version.split()[0]); print('Arch    :', platform.architecture()[0]); mods=['tkinter','pandas','openpyxl','xlrd','PyInstaller','pytest']; [print(f'{m:11}:', 'OK' if u.find_spec(m) else 'MISSING') for m in mods]"
goto end

rem ---------------------------------------------------------------------------
:run
"%PY%" app.py
goto end

rem ---------------------------------------------------------------------------
:test
"%PY%" -m pytest -q
if errorlevel 1 set "EXITCODE=1"
echo.
echo Note: this only covers utils.py/settings.py/field_map_store.py's pure
echo logic (see tests\). It does not exercise main.py's actual .p3/Excel I/O —
echo verify that by hand with "toolkit run" against sample data.
goto end

rem ---------------------------------------------------------------------------
:check
"%PY%" -c "import sys,platform,importlib.util as u; print('Python  :', sys.version.split()[0]); print('Arch    :', platform.architecture()[0]); mods=['tkinter','pandas','openpyxl','xlrd','PyInstaller','pytest']; [print(f'{m:11}:', 'OK' if u.find_spec(m) else 'MISSING') for m in mods]"
if errorlevel 1 set "EXITCODE=1"
goto end

rem ---------------------------------------------------------------------------
:package
rem The tests run first: a package that fails its own tests is not worth carrying.
"%PY%" -m pytest -q
if errorlevel 1 (
    echo Tests failed — packaging stopped. Fix them first.
    set "EXITCODE=1"
    goto end
)
if not exist "%~dp0.venv\Scripts\pyinstaller.exe" (
    echo PyInstaller is not installed in .venv — run "toolkit setup" first.
    set "EXITCODE=1"
    goto end
)
echo Building P3CC.exe from the committed P3CC.spec...
"%~dp0.venv\Scripts\pyinstaller.exe" P3CC.spec --noconfirm
if errorlevel 1 (
    echo Build failed. See the messages above.
    set "EXITCODE=1"
    goto end
)

for /f "delims=" %%v in ('"%PY%" -c "import config; print(config.VERSION)"') do set "VERSION=%%v"
if not defined VERSION set "VERSION=unknown"
set "ZIP_NAME=P3CC-v%VERSION%-portable.zip"

echo Zipping dist\P3CC into %ZIP_NAME% ...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\P3CC\*' -DestinationPath '%ZIP_NAME%' -Force"
if errorlevel 1 (
    echo Zipping failed. See the messages above.
    set "EXITCODE=1"
    goto end
)
echo.
echo Done: %ZIP_NAME%
echo Distribute this zip as a unit — never just P3CC.exe on its own.
goto end

rem ---------------------------------------------------------------------------
:end
if "%~1"=="" (
    echo.
    pause
)
endlocal & exit /b %EXITCODE%
