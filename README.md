# Evernote AI Note Rewriter

Automatically rewrites Evernote notes for clarity using Google Gemini. Drop a `.enex` file in the project folder, run the pipeline, and get back a fully rewritten version with improved readability — shorter sentences, plain-language analogies, and corrected grammar — while preserving all formatting, links, code blocks, and inline HTML exactly as they were. Also generates a separate key topics summary note for each notebook.

---

## Requirements

- Python 3.12+
- A Google Gemini API key ([get one at aistudio.google.com](https://aistudio.google.com))
- The `google-genai` and `beautifulsoup4` packages:

```
python -m pip install google-genai beautifulsoup4 lxml
```

### Set your API key

Set `GEMINI_API_KEY` as a permanent Windows environment variable:

1. Search **Environment Variables** in the Start menu
2. Click **Edit the system environment variables → Environment Variables**
3. Under **User variables**, click **New**
4. Variable name: `GEMINI_API_KEY` — Value: your actual key
5. Click OK and reopen your terminal

---

## Project structure

```
project/
│
├── run_workflow.bat          Main pipeline (full notebook run)
├── test_workflow.bat         Test pipeline (first N notes only)
│
├── extract_text.py           Step 1 — extracts text blocks from .enex
├── process_data.py           Step 2 — rewrites blocks via Gemini API
├── generate_summary.py       Step 3 — generates a key topics summary note
├── inject_text.py            Step 4 — injects rewritten text back into .enex
│
├── prompt.txt                Rewriting style instructions sent to Gemini
├── check_format.py           Utility — verifies ai_input.json is correctly formatted
├── compare_enex.py           Utility — compares original vs rewritten .enex files
│
├── YourNotebook.enex         Your source Evernote export (place here before running)
│
└── output/                   Working directory (created automatically)
    ├── YourNotebook.enex         Final rewritten note (ready to import)
    ├── YourNotebook_summary.enex Key topics summary note (ready to import)
    └── last_gemini_response_debug.json  Most recent Gemini output (survives cleanup)
```

---

## How to use

### Full run

1. Export a notebook or single note from Evernote as a `.enex` file and place it in the project folder
2. Double-click `run_workflow.bat` (or run it from a terminal)
3. When finished, both output files are in the `output\` folder — import them into Evernote

### Test run (quick prompt iteration)

Use this when tweaking `prompt.txt` and you want fast feedback without waiting on a full notebook:

```
test_workflow.bat          Process only the first note
test_workflow.bat 5        Process the first 5 notes
test_workflow.bat 10       Process the first 10 notes
```

The output note will contain rewritten text for the processed notes and original text for the rest. Intermediate files are left in `output\` after the run so you can inspect `ai_input.json` and `gemini-code-1.json` directly.

### Resuming a failed run

If the pipeline fails partway through (e.g. Gemini was unavailable for too long), progress made on completed chunks is automatically saved. Resume instead of starting over:

```
run_workflow.bat --resume
```

Extraction is skipped on a resume run since it was already done. Only the chunks that hadn't completed yet are sent to Gemini again.

---

## How it works

The pipeline runs in four steps:

**Step 1 — Extract** (`extract_text.py`)
Parses the `.enex` file and pulls every text block out of each note's content. Each block is classified as either a `bullet` (a term-definition style entry like `Term: definition` or `Term - definition`) or a `paragraph` (flowing prose). Blocks are replaced with numbered placeholders, and the skeleton structure is saved as a reference file. Three files are written to `output\`:
- `ai_input.json` — the extracted blocks with their type tags
- `note_boundaries.json` — which block IDs belong to which note
- `temp_tracked_reference.enex` — the skeleton .enex with placeholders

**Step 2 — Process** (`process_data.py`)
Reads the extracted blocks and sends them to Gemini 2.5 Flash for rewriting, using `prompt.txt` as the style guide. For large notebooks it splits the work into multiple batches, always keeping each note's blocks together so Gemini has full context. Progress is saved to disk after every batch, so a failure mid-run never loses completed work. Output is written to `output\gemini-code-1.json`.

**Step 3 — Summarize** (`generate_summary.py`)
Sends the rewritten content to Gemini and asks it to identify the 8–15 most important topics. Saves a standalone Evernote note with a bulleted list of key topics to `output\YourNotebook_summary.enex`. This step is non-fatal — if it fails, the main note pipeline continues.

**Step 4 — Inject** (`inject_text.py`)
Reads the tracked skeleton `.enex` and replaces every placeholder with the corresponding rewritten text from `gemini-code-1.json`. If a block has no rewritten version (e.g. during a partial test run), the original extracted text is restored instead so no placeholder is ever left visible. The final note is written to `output\YourNotebook.enex`.

---

## The rewriting prompt (`prompt.txt`)

The prompt controls exactly how Gemini rewrites the notes. Key rules it enforces:

- **Sentence length** — every sentence stays within 11–17 words, based on readability research showing comprehension drops sharply beyond that range
- **Plain-language framing** — concepts are introduced with real-world analogies before the technical definition (e.g. a JWT is a "digital ID badge" before it's a "compact, URL-safe object")
- **Cause-and-effect flow** — ideas are connected with reasoning words ("because," "so," "which means") rather than presented as disconnected facts
- **Bullet vs. paragraph handling** — each block's `type` field is used directly; bullets get light, surgical grammar and clarity fixes while staying concise; paragraphs get the full analogy and flow treatment
- **Structure preservation** — all inline HTML tags, links, code elements, class attributes, and non-English text are left completely untouched

You can edit `prompt.txt` directly to tune the rewriting style. Use `test_workflow.bat` with a small note count after any change to see the effect quickly before running the full notebook.

---

## Utilities

### `check_format.py`

Verifies that `output\ai_input.json` is in the correct tagged format (`{"type": ..., "text": ...}` per block) after extraction. Useful after updating `extract_text.py` to confirm the change took effect:

```
python check_format.py
```

### `compare_enex.py`

Compares the original source `.enex` against the final rewritten `.enex` block-by-block, reporting which blocks changed, which stayed the same, and the full text of both versions. Writes a report file named `comparison_report_<filename>.txt`:

```
python compare_enex.py YourNotebook.enex output\YourNotebook.enex
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'google'`**
Run `python -m pip install google-genai` (use `python -m pip` not just `pip` to ensure it installs into the same Python the pipeline uses).

**`GEMINI_API_KEY environment variable is not set`**
The key isn't set, or the terminal was opened before setting it. Close and reopen your terminal after setting the variable, then retry.

**`503 UNAVAILABLE` / Gemini is busy**
The pipeline retries automatically up to 20 times with increasing waits (up to 5 minutes per attempt, ~72 minutes total). If it still times out, wait a few minutes and rerun with `run_workflow.bat --resume`.

**`Gemini returned malformed JSON`**
Occasional model hiccup. The raw response is saved to `output\last_gemini_raw_response_chunk*.txt` for inspection. The pipeline retries automatically — if it keeps failing, check that file for clues.

**Final note block count is lower than the original**
Usually means the pipeline ran in test mode and only some notes were processed. The remaining blocks are restored from original text automatically, so no placeholders are left visible. Run the full `run_workflow.bat` to rewrite all notes.
