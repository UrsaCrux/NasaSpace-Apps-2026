@echo off
rem Field Shift launcher (Windows). Double-click it.
setlocal
set "HERE=%~dp0"
set "RUNTIME=%HERE%runtime"
call "%RUNTIME%\Scripts\activate.bat"
rem the first time: fix the paths of the bundled runtime for this folder
if not exist "%RUNTIME%\.unpacked" (
    echo Preparing Field Shift ^(first start, about a minute^)...
    "%RUNTIME%\Scripts\conda-unpack.exe" || exit /b 1
    type nul > "%RUNTIME%\.unpacked"
)
cd /d "%HERE%app"
start "Field Shift" "%RUNTIME%\pythonw.exe" -m fieldshift %*
endlocal
