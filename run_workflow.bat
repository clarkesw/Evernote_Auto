@echo off
setlocal enabledelayedexpansion

:: Define directory and script names
set "OUTPUT_DIR=output"
set "EXTRACT_SCRIPT=extract_text.py"
set "PROCESS_SCRIPT=process_data.py"
set "INJECT_SCRIPT=inject_text.py"
set "TEMP_ENEX=temp_tracked_reference.enex"
set "EXTRACT_JSON=ai_input.json"
set "SOURCE_NAME=source_filename.txt"

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
    del /f /q "%OUTPUT_DIR%\%TEMP_ENEX%"
    echo   - Removed temporary reference: %TEMP_ENEX%
)

if exist "%OUTPUT_DIR%\%EXTRACT_JSON%" (
    del /f /q "%OUTPUT_DIR%\%EXTRACT_JSON%"
    echo   - Removed initial extraction payload: %EXTRACT_JSON%
)

if exist "%OUTPUT_DIR%\%SOURCE_NAME%" (
    del /f /q "%OUTPUT_DIR%\%SOURCE_NAME%"
    echo   - Removed source filename reference: %SOURCE_NAME%
)

del /f /q "%OUTPUT_DIR%\gemini-code-*.json" >nul 2>&1
echo   - Flushed Gemini output payload from output directory.

echo =======================================================
echo Success! Final Evernote file ready inside '%OUTPUT_DIR%'
echo =======================================================
endlocal
exit /b 0

:error
echo =======================================================
echo Pipeline terminated due to an error. Temporary files preserved.
echo =======================================================
pause
exit /b 1
