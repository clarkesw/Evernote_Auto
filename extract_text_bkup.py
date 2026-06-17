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
        return
    
    enex_input_path = target_files[0]
    print(f"Processing source file: '{enex_input_path}'")
    
    tree = ET.parse(enex_input_path)
    root = tree.getroot()
    
    extracted_data = {}
    counter = 1
    
    for content_tag in root.iter('content'):
        if content_tag.text:
            # Open internal payload using a strict XML builder configuration
            soup = BeautifulSoup(content_tag.text, 'xml')
            
            # Target specific content text segments block containers
            blocks = soup.find_all(['div', 'p'])
            
            for block in blocks:
                # Extract text context across all internal text or style elements safely
                block_text = block.get_text().strip()
                
                if block_text and len(block_text.split()) > 3:
                    block_id = f"text_block_{counter}"
                    extracted_data[block_id] = block_text
                    
                    # Wipe nested children to set a unified string token
                    block.clear()
                    block.string = f"EVERNOTE_TEXT_BLOCK_PLACEHOLDER_{counter}"
                    counter += 1
            
            content_tag.text = str(soup)
            
    json_output_path = os.path.join(output_dir, json_filename)
    tracked_enex_path = os.path.join(output_dir, "temp_tracked_reference.enex")
        
    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(extracted_data, f, indent=2, ensure_ascii=False)
        
    tree.write(tracked_enex_path, encoding='utf-8', xml_declaration=True)
    print(f"Extraction complete! Payload exported to '{json_output_path}'")

if __name__ == "__main__":
    extract_enex_segments("output", "ai_input.json")