import os
import sys
import json
import time
import argparse
import threading
from google import genai
from google.genai import types
from google.genai import errors

# Configure your API token
# Best practice is to set an environment variable named GEMINI_API_KEY
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("Error: GEMINI_API_KEY environment variable is not set.")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

# Maximum characters of raw text-block content allowed per chunk before
# splitting into a new batch. This is a conservative proxy for staying
# well under Gemini's 65,536 output token ceiling, accounting for JSON
# structural overhead and the model's tendency to expand text slightly
# during rewriting. ~4 chars/token, budget kept well under the ceiling.
MAX_CHUNK_CHARS = 60000

def load_input_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_output_data(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def wait_with_heartbeat(seconds):
    for remaining in range(seconds, 0, -1):
        print(f"\r  Waiting... {remaining}s remaining ", end="", flush=True)
        time.sleep(1)
    print("\r  Resuming...                        ")

def call_with_heartbeat(model, contents, config):
    """
    Runs the Gemini API call in a background thread while printing a
    live elapsed-time heartbeat on the main thread, so the console
    never looks frozen while waiting for a response.
    """
    result = {}

    def worker():
        try:
            result["response"] = client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as e:
            result["error"] = e

    thread = threading.Thread(target=worker)
    thread.start()

    elapsed = 0
    while thread.is_alive():
        print(f"\r  Waiting on Gemini response... {elapsed}s elapsed ", end="", flush=True)
        time.sleep(1)
        elapsed += 1
    thread.join()
    print(f"\r  Gemini responded after {elapsed}s.                  ")

    if "error" in result:
        raise result["error"]
    return result["response"]

def split_into_chunks(payload_data, note_boundaries, max_chars=MAX_CHUNK_CHARS):
    """
    Splits the text_block_N dictionary into chunks that respect note
    boundaries: each chunk contains one or more *complete* notes, never
    a partial note, so Gemini sees full context when rewriting any
    block within a note. Notes are packed together by size until adding
    the next whole note would exceed max_chars, then a new chunk starts.

    If a single note's content alone exceeds max_chars, that note is
    split internally as a last resort (rather than failing outright),
    since one oversized note shouldn't be allowed to break the pipeline.

    If note_boundaries is empty/unavailable, falls back to simple
    block-by-block size splitting with no note awareness.
    """
    if not note_boundaries:
        # Fallback: no note boundary info available, split by raw size only.
        chunks = []
        current_chunk = {}
        current_size = 0
        for block_id, block in payload_data.items():
            block_size = len(block.get("text", "")) + len(block_id) + 30
            if current_chunk and (current_size + block_size > max_chars):
                chunks.append(current_chunk)
                current_chunk = {}
                current_size = 0
            current_chunk[block_id] = block
            current_size += block_size
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    chunks = []
    current_chunk = {}
    current_size = 0

    for note_block_ids in note_boundaries:
        note_size = sum(len(payload_data.get(bid, {}).get("text", "")) + len(bid) + 30 for bid in note_block_ids)

        if note_size > max_chars:
            # This single note alone is too big for one chunk. Flush
            # whatever's pending, then split this note internally by size.
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = {}
                current_size = 0

            sub_chunk = {}
            sub_size = 0
            for bid in note_block_ids:
                block = payload_data.get(bid, {})
                block_size = len(block.get("text", "")) + len(bid) + 30
                if sub_chunk and (sub_size + block_size > max_chars):
                    chunks.append(sub_chunk)
                    sub_chunk = {}
                    sub_size = 0
                sub_chunk[bid] = block
                sub_size += block_size
            if sub_chunk:
                chunks.append(sub_chunk)
            continue

        if current_chunk and (current_size + note_size > max_chars):
            chunks.append(current_chunk)
            current_chunk = {}
            current_size = 0

        for bid in note_block_ids:
            current_chunk[bid] = payload_data.get(bid, {})
        current_size += note_size

    if current_chunk:
        chunks.append(current_chunk)

    return chunks

def normalize_output(output_json):
    """
    Ensures every value in the returned dict is a plain string, even if
    Gemini ignores the formatting instruction and echoes back a
    {"type": ..., "text": ...} object instead. Defensive against
    inconsistent model output shape.
    """
    normalized = {}
    for block_id, value in output_json.items():
        if isinstance(value, dict):
            normalized[block_id] = value.get("text", "")
        else:
            normalized[block_id] = value
    return normalized

def process_chunk(chunk_data, system_instruction, chunk_num, total_chunks):
    """
    Sends a single chunk of text blocks to Gemini, with retry handling
    for transient errors, malformed JSON, and output truncation.
    Returns the parsed dict of rewritten blocks on success, or None if
    every retry attempt was exhausted without success. Does not exit
    the process -- the caller decides how to handle a failed chunk
    (e.g. saving progress made on earlier chunks before stopping).
    """
    full_prompt = (
        f"{system_instruction}\n\n"
        "### INPUT DATA FORMAT:\n"
        "Each entry below has a 'type' field ('bullet' or 'paragraph') and a 'text' field "
        "with the actual content to rewrite. Use the 'type' field to decide which rewrite "
        "rules apply (see rule 4 for 'bullet', and the Content & Style instructions for "
        "'paragraph'). Your response must be a flat JSON object mapping each text_block_X "
        "key directly to its rewritten text as a plain string -- do NOT include the 'type' "
        "field in your response, and do NOT wrap the rewritten text in another object.\n\n"
        f"### INPUT DATA:\n{json.dumps(chunk_data)}"
    )

    max_retries = 20
    base_delay = 30  # seconds, increases each attempt up to max_delay_cap
    max_delay_cap = 300  # never wait longer than 5 minutes between attempts

    for attempt in range(1, max_retries + 1):
        try:
            response = call_with_heartbeat(
                model="gemini-2.5-flash",
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=65536,
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                )
            )

            # Check whether the response was cut off due to hitting the
            # output token limit, which produces incomplete/invalid JSON.
            finish_reason = None
            try:
                finish_reason = response.candidates[0].finish_reason
            except (AttributeError, IndexError):
                pass

            if finish_reason is not None and str(finish_reason).upper().endswith("MAX_TOKENS"):
                print(f"Gemini's response was truncated (hit the output token limit).")
                if attempt < max_retries:
                    print(f"Retrying chunk {chunk_num}/{total_chunks} (attempt {attempt}/{max_retries})...")
                    wait_with_heartbeat(base_delay)
                    continue
                print("Repeated truncation on this chunk even after splitting. "
                      "Try lowering MAX_CHUNK_CHARS in process_data.py.")
                return None

            # Parse output response back to structured JSON data
            try:
                output_json = json.loads(response.text)
            except json.JSONDecodeError as je:
                # Save the raw, broken response so it can be inspected
                raw_path = os.path.join("output", f"last_gemini_raw_response_chunk{chunk_num}.txt")
                os.makedirs("output", exist_ok=True)
                with open(raw_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)

                print(f"Gemini returned malformed JSON: {je}")
                print(f"Raw response saved to: {raw_path}")

                if attempt < max_retries:
                    print(f"Retrying chunk {chunk_num}/{total_chunks} (attempt {attempt}/{max_retries})...")
                    wait_with_heartbeat(base_delay)
                    continue
                return None

            return normalize_output(output_json)

        except errors.APIError as e:
            is_retryable = getattr(e, "code", None) in (503, 429, 500)
            if is_retryable and attempt < max_retries:
                wait_time = min(base_delay * attempt, max_delay_cap)
                print(f"Gemini is busy (attempt {attempt}/{max_retries}). Retrying in {wait_time}s...")
                wait_with_heartbeat(wait_time)
                continue
            print(f"Error communicating with Gemini engine: {e}")
            return None

        except Exception as e:
            print(f"Error communicating with Gemini engine: {e}")
            return None

def main():
    parser = argparse.ArgumentParser(description="Send extracted note text to Gemini for rewriting.")
    parser.add_argument(
        "--test-chunks", type=int, default=None,
        help="If set, only process the first N chunks (after note-aware splitting) "
             "instead of the whole notebook. Useful for quick testing without waiting "
             "on a full large-notebook run."
    )
    parser.add_argument(
        "--test-notes", type=int, default=None,
        help="If set, only process the first N notes (by note boundary, before "
             "chunking) instead of the whole notebook. More precise than "
             "--test-chunks since it controls note count directly rather than "
             "chunk count. Cannot be combined with --test-chunks."
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="If set, load any existing gemini-code-1.json and skip chunks whose "
             "blocks are already fully present, only processing what's missing. "
             "Use this after a failed/interrupted run to continue instead of "
             "starting over and re-spending API calls on already-completed work."
    )
    args = parser.parse_args()

    if args.test_chunks is not None and args.test_notes is not None:
        print("Error: --test-chunks and --test-notes cannot be used together. Pick one.")
        sys.exit(1)

    input_file = os.path.join("output", "ai_input.json")
    output_file = os.path.join("output", "gemini-code-1.json")

    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    # Load your source text blocks
    payload_data = load_input_data(input_file)

    # Load system instruction from external prompt file
    prompt_file = "prompt.txt"
    if not os.path.exists(prompt_file):
        print(f"Error: {prompt_file} not found.")
        return
    with open(prompt_file, 'r', encoding='utf-8') as f:
        system_instruction = f.read()

    # Load note boundaries so chunking can keep each note's blocks together
    boundaries_file = os.path.join("output", "note_boundaries.json")
    note_boundaries = []
    if os.path.exists(boundaries_file):
        with open(boundaries_file, 'r', encoding='utf-8') as f:
            note_boundaries = json.load(f)
    else:
        print(f"Warning: {boundaries_file} not found. Falling back to size-only splitting (no note grouping).")

    if args.test_notes is not None:
        if not note_boundaries:
            print("Error: --test-notes requires note_boundaries.json, which was not found.")
            sys.exit(1)
        total_notes = len(note_boundaries)
        note_boundaries = note_boundaries[:args.test_notes]
        test_block_ids = {bid for note in note_boundaries for bid in note}
        payload_data = {bid: block for bid, block in payload_data.items() if bid in test_block_ids}
        print(f"TEST MODE: notebook has {total_notes} note(s) total, "
              f"only processing the first {len(note_boundaries)} note(s) "
              f"({len(payload_data)} blocks) for this test run.")
        print("Note: gemini-code-1.json will only contain rewritten text for the "
              "blocks in the processed note(s). Other blocks will be missing if "
              "you run inject_text.py against this partial output.")

    # Split into chunks if the notebook is large enough that a single
    # request risks truncating Gemini's output. Each chunk keeps whole
    # notes together so Gemini has full note context when rewriting.
    chunks = split_into_chunks(payload_data, note_boundaries)
    total_chunks = len(chunks)

    if args.test_chunks is not None:
        chunks = chunks[:args.test_chunks]
        print(f"TEST MODE: notebook has {total_chunks} chunk(s) total, "
              f"only processing the first {len(chunks)} for this test run.")
        print("Note: gemini-code-1.json will only contain rewritten text for the "
              "blocks in the processed chunk(s). Other blocks will be missing if "
              "you run inject_text.py against this partial output.")
    elif args.test_notes is not None:
        pass  # status already printed above when slicing note_boundaries
    elif total_chunks > 1:
        print(f"Notebook is large -- splitting into {total_chunks} batches to stay within Gemini's output limit.")
    else:
        print("Sending text data to Gemini API...")

    chunks_to_process = len(chunks)

    # Load any existing progress so a resumed run can skip completed chunks.
    merged_output = {}
    if args.resume and os.path.exists(output_file):
        merged_output = load_input_data(output_file)
        print(f"Resuming: loaded {len(merged_output)} already-completed block(s) from {output_file}.")

    any_failure = False
    for i, chunk in enumerate(chunks, start=1):
        chunk_block_ids = set(chunk.keys())

        if args.resume and chunk_block_ids.issubset(merged_output.keys()):
            print(f"\nSkipping batch {i}/{chunks_to_process} ({len(chunk)} blocks) -- already completed.")
            continue

        if chunks_to_process > 1 or args.test_chunks is not None or args.test_notes is not None:
            print(f"\nProcessing batch {i}/{chunks_to_process} ({len(chunk)} blocks)...")

        chunk_result = process_chunk(chunk, system_instruction, i, chunks_to_process)

        if chunk_result is None:
            any_failure = True
            print(f"\nChunk {i}/{chunks_to_process} failed after all retry attempts.")
            break

        merged_output.update(chunk_result)

        # Save progress immediately after every successful chunk, so a
        # later failure only risks the chunk in progress, not everything
        # completed so far.
        save_output_data(output_file, merged_output)
        debug_path = os.path.join("output", "last_gemini_response_debug.json")
        save_output_data(debug_path, merged_output)

    if any_failure:
        completed_blocks = len(merged_output)
        total_blocks = sum(len(c) for c in chunks)
        print(f"\nProgress saved: {completed_blocks}/{total_blocks} blocks completed in {output_file}.")
        print("Run this same command again with --resume added to continue "
              "from where it left off, e.g.:")
        print("    python process_data.py --resume")
        sys.exit(1)

    print(f"\nSuccess! System data updated and stored inside: {output_file}")

if __name__ == "__main__":
    main()
