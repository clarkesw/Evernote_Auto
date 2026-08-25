import glob
import json
import os
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

# Detects "Term:" or "Term - " style bulleted definitions by matching a
# short leading term (optionally with parentheses/quotes) followed by a
# colon or a standalone hyphen near the start of the block, then more
# text. Run against plain text (HTML tags stripped) so inline <b>/<a>
# wrappers around the term don't interfere with the match.
# Shared separator: a colon, or a dash (hyphen, en dash, or em dash)
# preceded by whitespace. Covers both "Term:" and "Term - " / "Term – "
# style leads regardless of which dash character was actually typed.
SEPARATOR = r'(:|\s[-\u2013\u2014])'

BULLET_PATTERN = re.compile(r'^[A-Za-z][\w \(\)\'"]{0,60}' + SEPARATOR + r'\s*\S')

# Same lead-in as BULLET_PATTERN, but specifically for a term whose
# trailing DASH is followed by nothing (or only trailing whitespace) --
# i.e. the term was set up for a definition that was never written, like
# "Read File -" with no text after the dash. Deliberately dash-only
# (not colon): a bare "Term:" with nothing after it (e.g. "Common
# Actions:") is typically a section heading introducing the bullets
# below it, not a term awaiting its own definition, so it should NOT be
# swept into this category and have content invented for it.
EMPTY_BULLET_PATTERN = re.compile(r'^[A-Za-z][\w \(\)\'"]{0,60}\s[-\u2013\u2014]\s*$')

# Matches a block that opens with a literal "Ex)" or "Fig)" marker. These
# read structurally like a bullet ("Ex) Paths class:" matches
# BULLET_PATTERN just as well as "Initialization:" does), but they are
# worked-example/figure callouts, not glossary term:definition entries --
# forcing them into the bullet type would expose the marker to the bullet
# rule's "fix grammar / clarify the term" instruction, which is exactly
# what caused "Ex)" to get expanded into "Example)" in practice.
EX_FIG_MARKER_PATTERN = re.compile(r'^(Ex|Fig)\)')

# Matches a block whose entire content is a short label ending in a colon
# with nothing after it -- e.g. "Storing Secrets:", "Jenkins/Build Jobs:",
# "Common Actions:". These are section headings that introduce whatever
# content follows in later sibling blocks, not a term awaiting its own
# inline definition (that's what EMPTY_BULLET_PATTERN is for, and it's
# dash-only for exactly this reason). Previously these fell through to
# "paragraph" by default, which let the full prose-rewrite treatment run
# on a two-word heading and silently strip its link/bold formatting as a
# side effect of "rewriting" content that should never have been touched.
HEADING_PATTERN = re.compile(r'^[A-Za-z][\w \(\)\'"/&-]{0,80}:\s*$')

# Heuristic signal that a block is actual source code rather than English
# prose that merely mentions code terms (e.g. "Override the clone() method").
# Requires BOTH a minimum density of code punctuation (braces or semicolons)
# AND at least one common code keyword, so ordinary prose sentences that use
# a stray parenthesis or single inline `code` term don't get misclassified.
CODE_KEYWORD_PATTERN = re.compile(
    r'\b(class|interface|public|private|protected|static|void|new|return|'
    r'throws|implements|extends|synchronized|volatile|final|import|package)\b'
)

def looks_like_code(html_text, child_line_count=0):
    """
    Returns True if a block's plain text reads as source code rather than
    prose. Used to catch real code blocks even when they have no
    distinguishing HTML wrapper (e.g. plain code pasted line-by-line into
    bare <div> tags, with no <pre>/<code> element at all), so they can be
    routed away from the prose-rewrite pipeline.

    Two independent signals, either of which is sufficient:

    1. STRUCTURAL (language-agnostic): code pasted into Evernote is
       almost always broken into one <div> per line (this is how the
       Singleton class ended up as one outer <div> wrapping 20+ inner
       <div> lines), which ordinary prose paragraphs never do. If a block
       has several such line-children AND a meaningful density of code
       punctuation (braces or parens), that's sufficient on its own --
       no keyword match required. This is what catches non-Java code
       (Groovy/Jenkinsfile DSL, YAML, Python, JS, SQL, etc.) that the
       keyword list below has no way to recognize by name.
    2. KEYWORD-BASED (Java-flavored fallback): for single-line or
       loosely-structured snippets without the multi-div signature,
       fall back to punctuation density plus a recognizable Java-style
       keyword, as before.
    """
    plain_text = BeautifulSoup(html_text, 'html.parser').get_text()
    brace_count = plain_text.count('{') + plain_text.count('}')
    paren_count = plain_text.count('(') + plain_text.count(')')
    semicolon_count = plain_text.count(';')
    keyword_hits = len(CODE_KEYWORD_PATTERN.findall(plain_text))

    if child_line_count >= 3 and (brace_count >= 2 or paren_count >= 2):
        return True

    return (brace_count >= 2 or semicolon_count >= 2) and keyword_hits >= 1

def get_table_position(cell):
    """
    Given a <td>/<th> cell, returns (row_index, col_index), both 0-based,
    describing its position within its enclosing <table>. Returns None if
    the cell isn't inside a <tr>/<table> structure BeautifulSoup can
    resolve. Used to identify header row (row_index == 0) and header
    column (col_index == 0) cells so they can be left untouched rather
    than run through the table_cell rewrite rules.
    """
    row = cell.find_parent('tr')
    if row is None:
        return None
    table = row.find_parent('table')
    if table is None:
        return None

    row_cells = row.find_all(['td', 'th'], recursive=False)
    col_index = next((i for i, c in enumerate(row_cells) if c is cell), None)

    all_rows = table.find_all('tr')
    row_index = next((i for i, r in enumerate(all_rows) if r is row), None)

    if col_index is None or row_index is None:
        return None
    return row_index, col_index

def strip_inner_xml_prolog(raw_content):
    """
    Evernote's <content> CDATA is itself a full standalone ENML document,
    complete with its own leading "<?xml ...?>" declaration and
    "<!DOCTYPE en-note ...>", typically preceded by indentation/whitespace
    from the outer export. That leading whitespace before the inner
    declaration is invalid per strict XML (a declaration must be the very
    first thing in a document) and, empirically, appears to push lxml's
    lenient recovery-mode parser into a state where it later silently
    drops content when it hits certain ambiguous character sequences
    (e.g. Java generics with inconsistently escaped angle brackets, like
    "Iterator&lt;Entry&lt;Integer, String>>", where the closing '>' was
    left unescaped in the source). BeautifulSoup doesn't need this inner
    declaration/DOCTYPE to parse the fragment -- stripping it before
    parsing avoids the desync entirely and has been confirmed to resolve
    real, reproducible data loss on affected notes.
    """
    return re.sub(r'^\s*<\?xml[^>]*\?>\s*<!DOCTYPE[^>]*>', '', raw_content)

def classify_block(html_text, in_table_cell=False, in_code_block=False, in_table_header=False):
    """
    Returns 'table_header' if the block sits in a table's header row or
    header column, 'table_cell' if it sits inside a <td>/<th> elsewhere in
    a table, 'code' if it reads as source code, 'paragraph' if it opens
    with a literal "Ex)"/"Fig)" marker (even if it would otherwise match
    the bullet pattern), 'heading' if it's a bare label ending in a colon
    with no content after it, 'bullet' if it looks like a
    'Term: definition' or 'Term - definition' style entry, otherwise
    'paragraph'. table_header, table_cell, code, Ex)/Fig), and heading
    status all take priority over bullet detection, since none of those
    should be routed into the glossary-style bullet rewrite rules or the
    full prose-rewrite treatment. Bullet classification is based on the
    block's plain text (HTML stripped) so it isn't thrown off by inline
    formatting tags around the leading term.
    """
    if in_table_header:
        return "table_header"
    if in_table_cell:
        return "table_cell"
    if in_code_block:
        return "code"
    plain_text = BeautifulSoup(html_text, 'html.parser').get_text().strip()
    if EX_FIG_MARKER_PATTERN.match(plain_text):
        return "paragraph"
    if HEADING_PATTERN.match(plain_text):
        return "heading"
    if EMPTY_BULLET_PATTERN.match(plain_text) or BULLET_PATTERN.match(plain_text):
        return "bullet"
    return "paragraph"

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
    note_boundaries = []  # list of lists of block_ids, one list per note
    counter = 1

    for content_tag in root.iter('content'):
        if content_tag.text:
            soup = BeautifulSoup(strip_inner_xml_prolog(content_tag.text), 'xml')

            # find_all matches every <div>/<p>, including ones nested inside
            # another matched <div>/<p> (e.g. a code block written as one
            # outer <div> wrapping a <div> per line). Without filtering,
            # that produces duplicate extraction: the whole block once as a
            # unit, then again broken into one entry per inner line. Keep
            # only the outermost match in each such chain.
            all_matches = soup.find_all(['div', 'p'])
            match_ids = {id(m) for m in all_matches}
            blocks = [
                m for m in all_matches
                if not any(id(ancestor) in match_ids for ancestor in m.parents)
            ]

            current_note_block_ids = []

            for block in blocks:
                # IMPORTANT: str(c) on a bare NavigableString does NOT escape
                # special characters at all (unlike str(Tag), which does).
                # For a plain-text div with no nested tags, block.contents is
                # just one NavigableString, so the old "".join(str(c) ...)
                # method silently produced literal, unescaped '<'/'>' in the
                # stored text -- e.g. Java generics like "Iterator<Entry<...>>"
                # went into the JSON exactly as-is. That reads to an LLM as a
                # broken/unclosed HTML tag, which is what was causing code
                # containing generics to get truncated during rewriting.
                # decode_contents() escapes plain text correctly while still
                # rendering real inline tags (e.g. <a href="...">, <code>) as
                # actual tags, so both cases are handled correctly at once.
                block_text = block.decode_contents().strip()

                # Normally a block needs more than one word to be worth
                # extracting. But a bare "Ex)"/"Fig)" marker with nothing
                # else -- exactly one token -- would otherwise be skipped
                # entirely and left permanently blank, since a block that's
                # never extracted never reaches the rewrite step at all.
                # Extract it anyway so the prompt's marker-expansion rule
                # gets a chance to fill it in.
                plain_text_for_check = block.get_text().strip()
                word_count = len(plain_text_for_check.split())
                is_bare_marker = bool(EX_FIG_MARKER_PATTERN.match(plain_text_for_check))

                if block_text and (word_count > 1 or is_bare_marker):
                    block_id = f"text_block_{counter}"

                    cell = block.find_parent(['td', 'th'])
                    in_table_cell = False
                    in_table_header = False
                    if cell is not None:
                        position = get_table_position(cell)
                        if position is not None:
                            row_index, col_index = position
                            if row_index == 0 or col_index == 0:
                                in_table_header = True
                            else:
                                in_table_cell = True
                        else:
                            # Couldn't resolve position (unexpected structure);
                            # fall back to treating it as a regular table cell
                            # rather than risk silently skipping table handling.
                            in_table_cell = True

                    child_line_count = len(block.find_all(['div', 'p'], recursive=False))
                    in_code_block = (not in_table_cell and not in_table_header) and looks_like_code(block_text, child_line_count)
                    block_type = classify_block(block_text, in_table_cell, in_code_block, in_table_header)
                    extracted_data[block_id] = {"type": block_type, "text": block_text}
                    current_note_block_ids.append(block_id)

                    block.clear()
                    block.string = f"EVERNOTE_TEXT_BLOCK_PLACEHOLDER_{counter}"
                    counter += 1

            content_tag.text = str(soup)
            if current_note_block_ids:
                note_boundaries.append(current_note_block_ids)

    json_output_path = os.path.join(output_dir, json_filename)
    tracked_enex_path = os.path.join(output_dir, "temp_tracked_reference.enex")

    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(extracted_data, f, indent=2, ensure_ascii=False)

    boundaries_path = os.path.join(output_dir, "note_boundaries.json")
    with open(boundaries_path, 'w', encoding='utf-8') as f:
        json.dump(note_boundaries, f, indent=2)

    tree.write(tracked_enex_path, encoding='utf-8', xml_declaration=True)

    # Save source filename so inject can use it for the final output name
    source_name_path = os.path.join(output_dir, "source_filename.txt")
    with open(source_name_path, 'w', encoding='utf-8') as f:
        f.write(enex_input_path)

    print(f"Extraction complete! Rich text layouts preserved in '{json_output_path}'")

if __name__ == "__main__":
    extract_enex_segments("output", "ai_input.json")
