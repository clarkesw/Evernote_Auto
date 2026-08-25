import glob
import json
import os
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

def inject_enex_segments(output_dir, final_output_dir=None):
    ET.register_namespace('', '')

    if final_output_dir is None:
        final_output_dir = output_dir

    tracked_enex_path = os.path.join(output_dir, "temp_tracked_reference.enex")
    source_name_path = os.path.join(output_dir, "source_filename.txt")

    # Read the original source filename and use it as the final output name
    if not os.path.exists(source_name_path):
        print("Error: Missing source filename reference inside the output directory.")
        return
    with open(source_name_path, 'r', encoding='utf-8') as f:
        source_filename = f.read().strip()

    if not os.path.exists(final_output_dir):
        os.makedirs(final_output_dir)
    final_enex_output_path = os.path.join(final_output_dir, source_filename)

    json_pattern = os.path.join(output_dir, "gemini-code-*.json")
    matching_json_files = glob.glob(json_pattern)

    if not matching_json_files:
        print(f"Error: No AI input data payloads matching pattern 'gemini-code-*.json' found inside '{output_dir}'.")
        return

    matching_json_files.sort(key=os.path.getmtime, reverse=True)
    ai_json_output_path = matching_json_files[0]
    print(f"Using dynamic input map payload: '{ai_json_output_path}'")

    if not os.path.exists(tracked_enex_path):
        print("Error: Missing mandatory tracking references inside the output directory.")
        return

    tree = ET.parse(tracked_enex_path)
    root = tree.getroot()

    with open(ai_json_output_path, 'r', encoding='utf-8') as f:
        ai_updates = json.load(f)

    # Load the original extracted text as a fallback, so that any block
    # not present in ai_updates (e.g. during a partial/test run, or if a
    # block was unexpectedly dropped) gets its original text restored
    # instead of leaving a literal placeholder string in the final note.
    original_input_path = os.path.join(output_dir, "ai_input.json")
    original_blocks = {}
    if os.path.exists(original_input_path):
        with open(original_input_path, 'r', encoding='utf-8') as f:
            raw_original = json.load(f)
        for block_id, value in raw_original.items():
            if isinstance(value, dict):
                original_blocks[block_id] = value.get("text", "")
            else:
                original_blocks[block_id] = value
    else:
        print(f"Warning: {original_input_path} not found. Unmatched placeholders "
              "(if any) cannot be restored to their original text.")

    missing_block_ids = []

    # Each <content> tag (one per note) gets its own unique marker token,
    # and its own resolved ENML payload, so multi-note notebooks don't
    # collide with each other during the final string replacement.
    payload_map = {}
    note_index = 0

    for content_tag in root.iter('content'):
        if content_tag.text:
            note_index += 1
            marker_token = f"__EVERNOTE_RAW_CDATA_MARKER_TOKEN_{note_index}__"

            soup = BeautifulSoup(content_tag.text, 'xml')

            # Find every placeholder actually present in this note, and
            # replace each one using the AI-rewritten text if available,
            # falling back to the original extracted text otherwise.
            # This ensures no literal placeholder string is ever left
            # behind, even for blocks missing from a partial test run.
            placeholder_re = re.compile(r'^EVERNOTE_TEXT_BLOCK_PLACEHOLDER_(\d+)$')
            placeholder_nodes = soup.find_all(string=placeholder_re)

            for target_node in placeholder_nodes:
                match = placeholder_re.match(str(target_node))
                counter_idx = match.group(1)
                block_id = f"text_block_{counter_idx}"

                if block_id in ai_updates:
                    updated_text = ai_updates[block_id]
                elif block_id in original_blocks:
                    updated_text = original_blocks[block_id]
                    missing_block_ids.append(block_id)
                else:
                    # No data anywhere for this block; leave it empty
                    # rather than keeping the raw placeholder string.
                    updated_text = ""
                    missing_block_ids.append(block_id)

                parent_block = target_node.parent
                parent_block.clear()

                # Read structural layouts safely without string escaping failures
                new_block_soup = BeautifulSoup(f"<div>{updated_text}</div>", 'xml')

                for child in list(new_block_soup.div.contents):
                    parent_block.append(child)

            en_note_element = soup.find('en-note')
            if en_note_element:
                raw_en_note = str(en_note_element)
            else:
                raw_en_note = str(soup)

            enml_payload = (
                '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
                '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">\n'
                f'{raw_en_note}'
            )

            payload_map[marker_token] = enml_payload
            content_tag.text = marker_token

    raw_xml_bytes = ET.tostring(root, encoding='utf-8')
    raw_xml_str = raw_xml_bytes.decode('utf-8')

    if not raw_xml_str.startswith('<?xml'):
        raw_xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + raw_xml_str

    final_output_string = raw_xml_str
    for marker_token, enml_payload in payload_map.items():
        cdata_safe_payload = f"<![CDATA[{enml_payload}]]>"
        final_output_string = final_output_string.replace(marker_token, cdata_safe_payload)

    with open(final_enex_output_path, 'w', encoding='utf-8') as f:
        f.write(final_output_string)

    print(f"Injection successful! Final document generated at '{final_enex_output_path}' ({note_index} notes processed)")
    if missing_block_ids:
        print(f"Note: {len(missing_block_ids)} block(s) had no AI-rewritten text "
              "(expected for a partial test run) and were restored using their "
              "original extracted text instead.")

if __name__ == "__main__":
    inject_enex_segments("output")
