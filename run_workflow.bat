@echo off
setlocal enabledelayedexpansion

:: Define directory and script names
set "OUTPUT_DIR=output"
set "EXTRACT_SCRIPT=extract_text.py"
set "PROCESS_SCRIPT=process_data.py"
set "INJECT_SCRIPT=inject_text.py"
set "TEMP_ENEX=temp_tracked_reference.enex"
set "EXTRACT_JSON=ai_input.json"
set "FINAL_ENEX=Final_Updated_Notes.enex"

echo =======================================================
echo Starting Evernote Text Transformation Pipeline
echo =======================================================

:: Step 1: Run Extraction Script
if not exist "%EXTRACT_SCRIPT%" (
    echo Error: %EXTRACT_SCRIPT% not found in the current directory.
    goto :error
)

echo [1/3] Running text extraction...
python "%EXTRACT_SCRIPT%"
if %ERRORLEVEL% neq 0 (
    echo Error: Extraction script failed.
    goto :error
)

:: Step 2: Run Gemini Processing Script
if not exist "%PROCESS_SCRIPT%" (
    echo Error: %PROCESS_SCRIPT% not found in the current directory.
    goto :error
)

echo.
echo [2/3] Sending extracted text to Gemini for processing...
python "%PROCESS_SCRIPT%"
if %ERRORLEVEL% neq 0 (
    echo Error: Gemini processing script failed.
    goto :error
)

:: Step 3: Run Injection Script
if not exist "%INJECT_SCRIPT%" (
    echo Error: %INJECT_SCRIPT% not found in the current directory.
    goto :error
)

echo.
echo [3/3] Running text injection...
python "%INJECT_SCRIPT%"
if %ERRORLEVEL% neq 0 (
    echo Error: Injection script failed.
    goto :error
)

:: Cleanup Intermediate Files
echo.
echo Cleaning up temporary files...

if exist "%OUTPUT_DIR%\%TEMP_ENEX%" (
REM     del /f /q "%OUTPUT_DIR%\%TEMP_ENEX%"
    echo   - Removed temporary reference: %TEMP_ENEX%
)

if exist "%OUTPUT_DIR%\%EXTRACT_JSON%" (
REM     del /f /q "%OUTPUT_DIR%\%EXTRACT_JSON%"
    echo   - Removed initial extraction payload: %EXTRACT_JSON%
)

:: Clear the dynamic json file used during this run
REM  del /f /q "%OUTPUT_DIR%\gemini-code-*.json" >nul 2>&1

echo   - Flushed raw input payload archives from target output directory.

echo =======================================================
echo Success! Final Evernote note ready: '%OUTPUT_DIR%\%FINAL_ENEX%'
echo =======================================================
goto :end

:error
echo =======================================================
echo Pipeline terminated due to an error. Temporary files preserved.
echo =======================================================
exit /b 1

:end
endlocal
pause
