How the Workflow Operates Now:

    Run Extraction: Your script creates ai_input.json (for the AI) and extracted_links_manifest.json (kept locally in the output folder).

    Consult the AI: Upload only ai_input.json. The AI reads the sentences containing markers like [LINK_MAPPING_1], rewrites the surrounding text to match your structural constraints, preserves those text tokens exactly where they belong in the new sentence structures, and gives you back the updated text mapping.

    Run Injection: When you save the AI's response as gemini-code-*.json and run your script, inject_text.py reads the AI's file, reads your local extracted_links_manifest.json tracker file, maps the structural elements together, swaps the tags back to clickable links, and cleans up the workspace.