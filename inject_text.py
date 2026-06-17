import glob
import json
import os
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

def inject_enex_segments(output_dir, final_filename):
    ET.register_namespace('', '')
    
    tracked_enex_path = os.path.join(output_dir, "temp_tracked_reference.enex")
    final_enex_output_path = os.path.join(output_dir, final_filename)
    
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
        
    for content_tag in root.iter('content'):
        if content_tag.text:
            soup = BeautifulSoup(content_tag.text, 'xml')
            
            for block_id, updated_text in ai_updates.items():
                counter_idx = block_id.split('_')[-1]
                placeholder = f"EVERNOTE_TEXT_BLOCK_PLACEHOLDER_{counter_idx}"
                
                target_node = soup.find(string=placeholder)
                if target_node:
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
            
            content_tag.text = "__EVERNOTE_RAW_CDATA_MARKER_TOKEN__"
            
    raw_xml_bytes = ET.tostring(root, encoding='utf-8')
    raw_xml_str = raw_xml_bytes.decode('utf-8')
    
    if not raw_xml_str.startswith('<?xml'):
        raw_xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + raw_xml_str
        
    cdata_safe_payload = f"<![CDATA[{enml_payload}]]>"
    final_output_string = raw_xml_str.replace("__EVERNOTE_RAW_CDATA_MARKER_TOKEN__", cdata_safe_payload)
        
    with open(final_enex_output_path, 'w', encoding='utf-8') as f:
        f.write(final_output_string)
        
    print(f"Injection successful! Final document generated at '{final_enex_output_path}'")

if __name__ == "__main__":
    inject_enex_segments("output", "Final_Updated_Notes.enex")