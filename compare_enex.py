import sys
import os
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

# python compare_enex.py Objects.enex ai_notes\Objects.enex
def extract_text_blocks(enex_path):
    """
    Extracts text content from each <content> tag in an .enex file,
    using the same block logic as extract_text.py (div/p elements with
    more than one word), so blocks line up consistently between files.
    """
    tree = ET.parse(enex_path)
    root = tree.getroot()

    blocks = []
    for note in root.iter('note'):
        title_tag = note.find('title')
        note_title = title_tag.text if title_tag is not None and title_tag.text else "(untitled note)"

        content_tag = note.find('content')
        if content_tag is None or not content_tag.text:
            continue

        soup = BeautifulSoup(content_tag.text, 'xml')
        elements = soup.find_all(['div', 'p'])

        for el in elements:
            text = el.get_text().strip()
            if text and len(text.split()) > 1:
                blocks.append((note_title, text))

    return blocks

def main():
    if len(sys.argv) != 3:
        print("Usage: python compare_enex.py <original.enex> <final.enex>")
        sys.exit(1)

    original_path = sys.argv[1]
    final_path = sys.argv[2]

    original_blocks = extract_text_blocks(original_path)
    final_blocks = extract_text_blocks(final_path)

    lines = []
    lines.append(f"Original file: {original_path} -> {len(original_blocks)} text blocks")
    lines.append(f"Final file:    {final_path} -> {len(final_blocks)} text blocks")
    lines.append("=" * 70)

    if len(original_blocks) != len(final_blocks):
        lines.append("WARNING: Block counts differ between files. Comparing by position anyway.")
        lines.append("")

    identical_count = 0
    changed_count = 0

    max_len = max(len(original_blocks), len(final_blocks))
    for i in range(max_len):
        orig_title, orig_text = original_blocks[i] if i < len(original_blocks) else ("(missing)", "")
        final_title, final_text = final_blocks[i] if i < len(final_blocks) else ("(missing)", "")

        if orig_text.strip() == final_text.strip():
            identical_count += 1
            status = "UNCHANGED"
        else:
            changed_count += 1
            status = "CHANGED"

        lines.append(f"[Block {i+1}] {status} (note: {orig_title})")
        if status == "CHANGED":
            lines.append(f"  ORIGINAL: {orig_text}")
            lines.append(f"  FINAL:    {final_text}")
        else:
            lines.append(f"  TEXT: {orig_text}")
        lines.append("")

    lines.append("=" * 70)
    lines.append(f"Summary: {identical_count} unchanged, {changed_count} changed, {max_len} total blocks")

    if identical_count == max_len:
        lines.append("\n*** ALL BLOCKS ARE IDENTICAL. The injection step likely did not apply Gemini's edits. ***")
    elif changed_count == max_len:
        lines.append("\n*** ALL BLOCKS CHANGED. The pipeline appears to be working correctly. ***")
    else:
        lines.append(f"\n*** PARTIAL CHANGE. {changed_count}/{max_len} blocks were updated. Check the UNCHANGED blocks above for patterns. ***")

    report_text = "\n".join(lines)

    # Write the full report to a file
    final_basename = os.path.splitext(os.path.basename(final_path))[0]
    report_path = f"comparison_report_{final_basename}.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)

    # Print a short summary to the console
    print(f"Original file: {original_path} -> {len(original_blocks)} text blocks")
    print(f"Final file:    {final_path} -> {len(final_blocks)} text blocks")
    print(f"Summary: {identical_count} unchanged, {changed_count} changed, {max_len} total blocks")
    print(f"\nFull report written to: {report_path}")

if __name__ == "__main__":
    main()
