@echo off
setlocal enabledelayedexpansion

:: ===========================================================
:: TEST WORKFLOW - processes only the first N notes (default 1)
:: so you can quickly check prompt/formatting changes without
:: waiting on a full notebook run.
::
:: Usage:
::   test_workflow.bat            (defaults to 1 note)
::   test_workflow.bat 5          (processes first 5 notes)
:: ===========================================================

set "OUTPUT_DIR=output"
set "EXTRACT_SCRIPT=extract_text.py"
set "PROCESS_SCRIPT=process_data.py"
set "INJECT_SCRIPT=inject_text.py"

set "NOTE_COUNT=%~1"
if "%NOTE_COUNT%"=="" set "NOTE_COUNT=1"

echo =======================================================
echo Starting TEST run (first %NOTE_COUNT% note(s) only)
echo =======================================================

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

if not exist "%PROCESS_SCRIPT%" (
    echo Error: %PROCESS_SCRIPT% not found in the current directory.
    goto :error
)

echo.
echo [2/3] Sending ONLY the first %NOTE_COUNT% note(s) to Gemini for processing...
python "%PROCESS_SCRIPT%" --test-notes %NOTE_COUNT%
if %ERRORLEVEL% neq 0 (
    echo Error: Gemini processing script failed.
    goto :error
)

if not exist "%INJECT_SCRIPT%" (
    echo Error: %INJECT_SCRIPT% not found in the current directory.
    goto :error
)

echo.
echo [3/3] Running text injection...
echo NOTE: since only %NOTE_COUNT% note(s) were processed, any other
echo notes will be MISSING from the final note. This is expected
echo for a quick test run -- use run_workflow.bat for the real thing.
python "%INJECT_SCRIPT%"
if %ERRORLEVEL% neq 0 (
    echo Error: Injection script failed.
    goto :error
)

echo =======================================================
echo Test run complete! Check ai_notes for partial output.
echo Intermediate files in 'output' were left in place
echo so you can inspect ai_input.json / gemini-code-1.json directly.
echo =======================================================
endlocal
exit /b 0

:error
echo =======================================================
echo Test run terminated due to an error.
echo =======================================================
pause
exit /b 1
