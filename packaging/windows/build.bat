@echo off
rem Construit dist\mpp2mindview-gui.exe et dist\mpp2mindview.exe sous Windows.
rem Prerequis : Python 3.12 (ou 3.13) installe depuis python.org, avec le lanceur "py".
setlocal
cd /d "%~dp0\..\.."

set PYVER=%1
if "%PYVER%"=="" set PYVER=3.12

where py >nul 2>nul
if errorlevel 1 (
    echo Lanceur Python "py" introuvable. Installez Python %PYVER% depuis https://www.python.org
    exit /b 1
)

echo === Environnement virtuel Python %PYVER%
py -%PYVER% -m venv .venv-win || exit /b 1
call .venv-win\Scripts\activate.bat || exit /b 1

echo === Installation des dependances
python -m pip install --upgrade pip || exit /b 1
python -m pip install ".[gui,dev]" pyinstaller || exit /b 1

echo === Tests
python -m pytest -q || exit /b 1

echo === Construction des executables
pyinstaller --noconfirm --clean packaging\windows\mpp2mindview.spec || exit /b 1

echo === Verification rapide
dist\mpp2mindview.exe tests\fixtures\task-links-project2010-mpp14.mpp -o "%TEMP%\mpp2mindview-test.xml" -f || exit /b 1

echo.
echo Termine : dist\mpp2mindview-gui.exe et dist\mpp2mindview.exe
endlocal
