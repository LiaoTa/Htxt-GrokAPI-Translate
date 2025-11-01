@echo off
setlocal
set "PYTHONIOENCODING=utf-8"
chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"
set "PYTHON_CMD="
set "PORTABLE_DIR=%SCRIPT_DIR%python-3.11.9-embed-amd64"
if exist "%PORTABLE_DIR%\python.exe" (
    set "PYTHON_CMD=%PORTABLE_DIR%\python.exe"
    set "PYTHONHOME=%PORTABLE_DIR%"
    set "PYTHONPATH=%PORTABLE_DIR%\python311.zip;%PORTABLE_DIR%;%PORTABLE_DIR%\Lib;%PORTABLE_DIR%\Lib\site-packages"
)
if not defined PYTHON_CMD if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    set "PYTHON_CMD=%SCRIPT_DIR%venv\Scripts\python.exe"
)
if defined PYTHON_CMD goto run
for %%I in (python.exe py.exe) do (
    where %%I >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=%%I"
        goto run
    )
)
echo 未找到 Python 執行檔，請先安裝或設定 PATH。
set "ERR=1"
goto done
:run
pushd "%SCRIPT_DIR%"
%PYTHON_CMD% "5_stepa_txt_to_stepb_html(en).py" %*
set "ERR=%ERRORLEVEL%"
popd
goto done

:done
echo.
echo 執行已結束，按任意鍵以繼續...
pause
exit /b %ERR%

