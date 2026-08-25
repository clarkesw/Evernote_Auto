import json
import os
import sys

def main():
    path = os.path.join("output", "ai_input.json")

    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data:
        print("ai_input.json is empty.")
        sys.exit(1)

    first_key = next(iter(data))
    first_value = data[first_key]

    print(f"Total blocks: {len(data)}")
    print(f"First key: {first_key}")
    print(f"First value type: {type(first_value).__name__}")
    print()

    if isinstance(first_value, dict):
        print("RESULT: NEW FORMAT (tagged) -- {'type': ..., 'text': ...}")
        print(f"  type: {first_value.get('type')}")
        print(f"  text: {str(first_value.get('text'))[:100]}")
    elif isinstance(first_value, str):
        print("RESULT: OLD FORMAT (plain string)")
        print(f"  value: {first_value[:100]}")
    else:
        print(f"RESULT: UNEXPECTED FORMAT -- value is a {type(first_value).__name__}")

    # Also scan the whole file in case it's a mix (shouldn't happen, but worth checking)
    str_count = sum(1 for v in data.values() if isinstance(v, str))
    dict_count = sum(1 for v in data.values() if isinstance(v, dict))
    print()
    print(f"Blocks as plain strings: {str_count}")
    print(f"Blocks as tagged dicts:  {dict_count}")
    if str_count > 0 and dict_count > 0:
        print("\nWARNING: file contains a MIX of old and new format blocks.")

if __name__ == "__main__":
    main()
