import os
import sys
import json
import time
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

def main():
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

    # Combine the system prompt framework and the user content payload
    full_prompt = f"{system_instruction}\n\n### INPUT DATA:\n{json.dumps(payload_data)}"

    print("Sending text data to Gemini API...")
    max_retries = 10
    base_delay = 30  # seconds, increases each attempt

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            # Parse output response back to structured JSON data
            output_json = json.loads(response.text)
            save_output_data(output_file, output_json)

            # Save a permanent debug copy that survives cleanup, for comparison
            debug_path = os.path.join("output", "last_gemini_response_debug.json")
            save_output_data(debug_path, output_json)

            print(f"Success! System data updated and stored inside: {output_file}")
            return

        except errors.APIError as e:
            is_retryable = getattr(e, "code", None) in (503, 429, 500)
            if is_retryable and attempt < max_retries:
                wait_time = base_delay * attempt
                print(f"Gemini is busy (attempt {attempt}/{max_retries}). Retrying in {wait_time}s...")
                wait_with_heartbeat(wait_time)
                continue
            print(f"Error communicating with Gemini engine: {e}")
            sys.exit(1)

        except Exception as e:
            print(f"Error communicating with Gemini engine: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
