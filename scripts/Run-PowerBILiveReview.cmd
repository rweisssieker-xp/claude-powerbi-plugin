@echo off
rem Claude Power BI Live Review (read-only). Double-click with one or more models open in Power BI Desktop.
rem Optional arguments: [output folder] [part of the window title to review only that model]
setlocal
set "SCRIPTS=%~dp0"
set "OUT=%~1"
if "%OUT%"=="" set "OUT=%USERPROFILE%\Documents\PowerBI-Live-Review"
set "PS=powershell"
where pwsh >nul 2>&1 && set "PS=pwsh"
if exist "%OUT%\DONE.txt" del "%OUT%\DONE.txt"
echo Reviewing open Power BI Desktop models (read-only)...
if "%~2"=="" (
  %PS% -NoProfile -ExecutionPolicy Bypass -File "%SCRIPTS%Invoke-PowerBILiveReviewAll.ps1" -OutputDirectory "%OUT%" > "%OUT%.log" 2>&1
) else (
  %PS% -NoProfile -ExecutionPolicy Bypass -File "%SCRIPTS%Invoke-PowerBILiveReviewAll.ps1" -OutputDirectory "%OUT%" -Title "%~2" > "%OUT%.log" 2>&1
)
echo finished %DATE% %TIME% > "%OUT%\DONE.txt"
echo.
echo Done. Results: %OUT%\index.md
timeout /t 8
