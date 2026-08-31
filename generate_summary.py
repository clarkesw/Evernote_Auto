import os
import sys
import json
import time
import threading
from datetime import datetime, timezone
from google import genai
from google.genai import types
from google.genai import errors

# Configure your API token
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("Error: GEMINI_API_KEY environment variable is not set.")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

def wait_with_heartbeat(seconds):
    for remaining in range(seconds, 0, -1):
        print(f"\r  Waiting... {remaining}s remaining ", end="", flush=True)
        time.sleep(1)
    print("\r  Resuming...                        ")

def call_with_heartbeat(model, contents, config):
    """
    Runs the Gemini API call in a background thread while printing a
    live elapsed-time heartbeat on the main thread.
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

def escape_xml(text):
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )

def build_summary_enex(note_title, topics):
    """
    Builds a minimal, standalone, valid .enex file containing a single
    note with a bulleted list of topics. Independent of the main
    extract/inject pipeline -- does not touch temp_tracked_reference.enex
    or any other pipeline state.
    """
    created = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    list_items = "".join(f"<li>{escape_xml(topic)}</li>" for topic in topics)

    en_note_body = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
        '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
        f'<en-note><ul>{list_items}</ul></en-note>'
    )

    enex_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE en-export SYSTEM "http://xml.evernote.com/pub/evernote-export3.dtd">
<en-export export-date="{created}" application="Evernote" version="10.x">
<note>
<title>{escape_xml(note_title)}</title>
<content><![CDATA[{en_note_body}]]></content>
<created>{created}</created>
<updated>{created}</updated>
</note>
</en-export>
'''
    return enex_content

def main():
    gemini_json_path = os.path.join("output", "gemini-code-1.json")
    source_name_path = os.path.join("output", "source_filename.txt")

    if not os.path.exists(gemini_json_path):
        print(f"Error: {gemini_json_path} not found. Skipping topic summary.")
        return

    if not os.path.exists(source_name_path):
        print(f"Error: {source_name_path} not found. Skipping topic summary.")
        return

    with open(gemini_json_path, 'r', encoding='utf-8') as f:
        rewritten_blocks = json.load(f)

    with open(source_name_path, 'r', encoding='utf-8') as f:
        source_filename = f.read().strip()

    source_basename = os.path.splitext(source_filename)[0]

    combined_text = "\n".join(rewritten_blocks.values())

    prompt = (
        "You will be given the text content of a notebook of study notes. "
        "Identify the most important topics covered across all the notes. "
        "Return ONLY a JSON array of short topic strings, each one a concise "
        "phrase (3-8 words) naming a key topic or concept. "
        "Order them by importance, most important first. "
        "Limit the list to the 8-15 most important topics. "
        "Do not include any commentary, only the raw JSON array.\n\n"
        f"### NOTES CONTENT:\n{combined_text}"
    )

    print("Generating topic summary with Gemini...")
    max_retries = 5
    base_delay = 30

    for attempt in range(1, max_retries + 1):
        try:
            response = call_with_heartbeat(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            try:
                topics = json.loads(response.text)
            except json.JSONDecodeError as je:
                print(f"Gemini returned malformed JSON: {je}")
                if attempt < max_retries:
                    print(f"Retrying (attempt {attempt}/{max_retries})...")
                    wait_with_heartbeat(base_delay)
                    continue
                print("Skipping topic summary after repeated failures.")
                return

            if not isinstance(topics, list) or not topics:
                print("Gemini did not return a valid topic list. Skipping summary.")
                return

            note_title = f"{source_basename} - Key Topics Summary"
            enex_output = build_summary_enex(note_title, topics)

            final_output_dir = "output/summary"
            if not os.path.exists(final_output_dir):
                os.makedirs(final_output_dir)

            output_path = os.path.join(final_output_dir, f"{source_basename}_summary.enex")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(enex_output)

            print(f"Topic summary created: {output_path}")
            return

        except errors.APIError as e:
            is_retryable = getattr(e, "code", None) in (503, 429, 500)
            if is_retryable and attempt < max_retries:
                wait_time = base_delay * attempt
                print(f"Gemini is busy (attempt {attempt}/{max_retries}). Retrying in {wait_time}s...")
                wait_with_heartbeat(wait_time)
                continue
            print(f"Error communicating with Gemini engine: {e}")
            print("Skipping topic summary.")
            return

        except Exception as e:
            print(f"Error generating topic summary: {e}")
            print("Skipping topic summary.")
            return

if __name__ == "__main__":
    main()
