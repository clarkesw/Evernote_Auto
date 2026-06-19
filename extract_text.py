import glob
import json
import os
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

def extract_enex_segments(output_dir, json_filename):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    enex_files = glob.glob("*.enex")
    excluded_files = {"temp_tracked_reference.enex", "Final_Updated_Notes.enex"}
    target_files = [f for f in enex_files if f not in excluded_files]

    if not target_files:
        print("Error: No source ENEX files found.")
        return None

    enex_input_path = target_files[0]
    print(f"Processing source file: '{enex_input_path}'")

    tree = ET.parse(enex_input_path)
    root = tree.getroot()

    extracted_data = {}
    counter = 1

    for content_tag in root.iter('content'):
        if content_tag.text:
            soup = BeautifulSoup(content_tag.text, 'xml')
            blocks = soup.find_all(['div', 'p'])

            for block in blocks:
                block_text = "".join([str(c) for c in block.contents]).strip()

                if block_text and len(block.get_text().split()) > 1:
                    block_id = f"text_block_{counter}"
                    extracted_data[block_id] = block_text

                    block.clear()
                    block.string = f"EVERNOTE_TEXT_BLOCK_PLACEHOLDER_{counter}"
                    counter += 1

            content_tag.text = str(soup)

    json_output_path = os.path.join(output_dir, json_filename)
    tracked_enex_path = os.path.join(output_dir, "temp_tracked_reference.enex")

    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(extracted_data, f, indent=2, ensure_ascii=False)

    tree.write(tracked_enex_path, encoding='utf-8', xml_declaration=True)

    # Save source filename so inject can use it for the final output name
    source_name_path = os.path.join(output_dir, "source_filename.txt")
    with open(source_name_path, 'w', encoding='utf-8') as f:
        f.write(enex_input_path)

    print(f"Extraction complete! Rich text layouts preserved in '{json_output_path}'")

if __name__ == "__main__":
    extract_enex_segments("output", "ai_input.json")
