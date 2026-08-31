@echo off
setlocal enabledelayedexpansion

:: Define directory and script names
set "OUTPUT_DIR=output"
set "EXTRACT_SCRIPT=extract_text.py"
set "PROCESS_SCRIPT=process_data.py"
set "SUMMARY_SCRIPT=generate_summary.py"
set "INJECT_SCRIPT=inject_text.py"
set "TEMP_ENEX=temp_tracked_reference.enex"
set "EXTRACT_JSON=ai_input.json"
set "SOURCE_NAME=source_filename.txt"
set "NOTE_BOUNDARIES=note_boundaries.json"

set "RESUME_FLAG="
if /I "%~1"=="--resume" set "RESUME_FLAG=--resume"

echo =======================================================
echo Starting Evernote Text Transformation Pipeline
echo =======================================================

:: Step 1: Run Extraction Script (skipped when resuming a previous run)
if not "%RESUME_FLAG%"=="" (
    echo [1/4] Skipping extraction -- resuming previous run.
) else (
    if not exist "%EXTRACT_SCRIPT%" (
        echo Error: %EXTRACT_SCRIPT% not found in the current directory.
        goto :error
    )

    echo [1/4] Running text extraction...
    python "%EXTRACT_SCRIPT%"
    if %ERRORLEVEL% neq 0 (
        echo Error: Extraction script failed.
        goto :error
    )
)

:: Step 2: Run Gemini Processing Script
if not exist "%PROCESS_SCRIPT%" (
    echo Error: %PROCESS_SCRIPT% not found in the current directory.
    goto :error
)

echo.
echo [2/4] Sending extracted text to Gemini for processing...
python "%PROCESS_SCRIPT%" %RESUME_FLAG%
if %ERRORLEVEL% neq 0 (
    echo Error: Gemini processing script failed partway through.
    goto :resume_error
)

:: Step 3: Generate Topic Summary (does not affect the main note pipeline)
if not exist "%SUMMARY_SCRIPT%" (
    echo Warning: %SUMMARY_SCRIPT% not found. Skipping topic summary.
) else (
    echo.
    echo [3/4] Generating topic summary note...
    python "%SUMMARY_SCRIPT%"
    if %ERRORLEVEL% neq 0 (
        echo Warning: Topic summary generation failed. Continuing with main pipeline.
    )
)

:: Step 4: Run Injection Script
if not exist "%INJECT_SCRIPT%" (
    echo Error: %INJECT_SCRIPT% not found in the current directory.
    goto :error
)

echo.
echo [4/4] Running text injection...
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

if exist "%OUTPUT_DIR%\%NOTE_BOUNDARIES%" (
    del /f /q "%OUTPUT_DIR%\%NOTE_BOUNDARIES%"
    echo   - Removed note boundary reference: %NOTE_BOUNDARIES%
)

del /f /q "%OUTPUT_DIR%\gemini-code-*.json" >nul 2>&1
del "*.enex"
echo   - Flushed Gemini output payload from output directory.

echo =======================================================
echo Success! Final Evernote file and topic summary are
echo ready inside '%OUTPUT_DIR%'
echo =======================================================
endlocal
exit /b 0

:resume_error
echo =======================================================
echo Pipeline terminated due to an error during Gemini processing.
echo Progress made so far was saved.
echo.
echo To continue instead of starting over, run:
echo     run_workflow.bat --resume
echo =======================================================
pause
exit /b 1

:error
echo =======================================================
echo Pipeline terminated due to an error.
echo =======================================================
pause
exit /b 1
