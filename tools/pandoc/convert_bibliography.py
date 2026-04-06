#!/usr/bin/env python3
"""
Convert LaTeX thebibliography environment to plain paragraphs for Pandoc DOCX conversion.
This ensures references are preserved in the Word document output.
"""

import sys
import re

def convert_bibliography(latex_content):
    """
    Convert \begin{thebibliography}...\end{thebibliography} to plain paragraphs.
    Each \bibitem becomes a regular paragraph that Pandoc will preserve.
    """

    # Find the bibliography section
    bib_pattern = r'\\begin\{thebibliography\}\{[^}]*\}(.*?)\\end\{thebibliography\}'

    def process_bibliography(match):
        bib_content = match.group(1)

        # Split by \bibitem
        items = re.split(r'\\bibitem', bib_content)

        result = []
        result.append('\n\\section*{References}\n\n')

        for item in items[1:]:  # Skip first empty split
            # Extract optional label and key
            # Pattern: [Author (Year)]{key} followed by content
            item_match = re.match(r'\s*\[([^\]]+)\]\{[^}]+\}(.*)', item, re.DOTALL)
            if item_match:
                # Keep just the content, Pandoc will handle the rest
                content = item_match.group(2).strip()
                # Just output as regular paragraphs - no special formatting
                result.append(content)
                result.append('\n\n')

        return ''.join(result)

    # Replace the bibliography
    converted = re.sub(bib_pattern, process_bibliography, latex_content, flags=re.DOTALL)

    return converted

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: convert_bibliography.py input.tex output.tex")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    converted = convert_bibliography(content)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(converted)

    print(f"Converted bibliography from {input_file} to {output_file}")
