#!/usr/bin/env bash
# Create final_manuscript/*.docx from final_manuscript/*.tex using Pandoc.
# - Converts figure PDFs to PNGs for Word
# - Optional siunitx Lua filter (if present)
# - Downgrades algorithm floats for clean docx output
# - Auto-detects citeproc support (built-in vs pandoc-citeproc)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEX="${1:-$ROOT/final_manuscript/final_manuscript.tex}"
OUTDOCX="${2:-$ROOT/final_manuscript/final_manuscript.docx}"

FIGDIR="$ROOT/final_manuscript/figures"
TMPDIR="$ROOT/.pandoc_tmp"
FILTER_DIR="$ROOT/tools/pandoc"
SI_FILTER="$FILTER_DIR/siunitx.lua"
REFDOC="$ROOT/tools/asce-reference.docx"   # optional reference formatting doc

have_cmd() { command -v "$1" >/dev/null 2>&1; }

# --- Check pandoc is installed ---
if ! have_cmd pandoc; then
  echo "ERROR: pandoc not found in PATH." >&2
  exit 1
fi

# --- Detect citeproc capability ---
# IMPORTANT: Only use citeproc if the document uses BibTeX/BibLaTeX (.bib file)
# If the document has an embedded bibliography (\begin{thebibliography}),
# skip citeproc to let Pandoc convert it natively
CITEPROC_MODE="none"

# Check if document has embedded bibliography
if grep -q '\\begin{thebibliography}' "$TEX"; then
  echo "Note: Detected embedded bibliography; skipping citeproc to preserve references."
  CITEPROC_MODE="none"
elif pandoc --help 2>&1 | grep -q -- '--citeproc'; then
  CITEPROC_MODE="builtin"      # Pandoc >= 2.11
elif have_cmd pandoc-citeproc; then
  CITEPROC_MODE="filter"       # Older Pandoc + external filter
else
  CITEPROC_MODE="none"         # No citation processing possible
fi

# --- Pandoc options ---
# Configure for ASCE formatting:
# - 12pt Times New Roman font (via reference doc if available)
# - 1 inch margins (via reference doc if available)
# - Single spacing (via reference doc if available)
# - Page numbers in footer only
# Note: DOCX formatting is best controlled via --reference-doc
# Variables like fontsize, geometry work for LaTeX but not DOCX
PANDOC_OPTS=(
  --standalone
  --from=latex+raw_tex
  --to=docx
  --resource-path="$ROOT:$ROOT/final_manuscript:$FIGDIR:$ROOT/manuscript_results"
  --metadata=link-citations:true
)

case "$CITEPROC_MODE" in
  builtin)
    PANDOC_OPTS+=(--citeproc)
    ;;
  filter)
    PANDOC_OPTS+=(--filter pandoc-citeproc)
    ;;
  none)
    # Only warn if we don't have embedded bibliography
    if ! grep -q '\\begin{thebibliography}' "$TEX"; then
      echo "WARNING: Neither --citeproc nor pandoc-citeproc available; citations will not be processed." >&2
    fi
    ;;
esac

# Optional reference docx
if [ -f "$REFDOC" ]; then
  PANDOC_OPTS+=(--reference-doc="$REFDOC")
fi

# Optional Lua filter for siunitx (only if file exists)
if [ -f "$SI_FILTER" ]; then
  PANDOC_OPTS+=(--lua-filter="$SI_FILTER")
else
  echo "Note: $SI_FILTER not found; skipping siunitx Lua filter." >&2
fi

echo "==> Building DOCX from: $TEX"
[ -f "$TEX" ] || { echo "ERROR: $TEX not found"; exit 1; }

# 1) Ensure PNGs exist for every PDF figure (Word can't embed PDFs)
mkdir -p "$FIGDIR"
shopt -s nullglob
pdfs=("$FIGDIR"/*.pdf)
if [ ${#pdfs[@]} -gt 0 ]; then
  echo "==> Converting PDF figures to PNG (for Word)..."
  for pdf in "${pdfs[@]}"; do
    base="${pdf%.pdf}"
    png="${base}.png"
    if [ ! -f "$png" ]; then
      if have_cmd magick; then
        magick -density 300 "$pdf" -quality 92 "$png"
      elif have_cmd pdftoppm; then
        pdftoppm -png -r 300 "$pdf" "${base}"
        [ -f "${base}-1.png" ] && mv "${base}-1.png" "$png"
      elif have_cmd gs; then
        gs -dSAFER -dBATCH -dNOPAUSE -sDEVICE=pngalpha -r300 \
           -sOutputFile="$png" "$pdf"
      else
        echo "  ⚠ No converter found (need ImageMagick 'magick', 'pdftoppm' or 'gs'). Skipping $pdf"
      fi
    fi
  done
fi

# 2) Make a temp .tex with light adjustments for Pandoc
mkdir -p "$TMPDIR" "$FILTER_DIR"
TMP_TEX="$TMPDIR/for_docx.tex"
TMP_TEX_INTERMEDIATE="$TMPDIR/intermediate.tex"

# - turn algorithm floats into figures (Pandoc-friendly)
sed -E \
  -e 's/\\begin\{algorithm\}(\[[^]]*\])?/\\begin{figure}/g' \
  -e 's/\\end\{algorithm\}/\\end{figure}/g' \
  "$TEX" > "$TMP_TEX_INTERMEDIATE"

# - convert thebibliography to plain paragraphs so Pandoc preserves it in DOCX
if [ -f "$FILTER_DIR/convert_bibliography.py" ] && grep -q '\\begin{thebibliography}' "$TMP_TEX_INTERMEDIATE"; then
  python3 "$FILTER_DIR/convert_bibliography.py" "$TMP_TEX_INTERMEDIATE" "$TMP_TEX"
  echo "Note: Converted embedded bibliography to plain format for DOCX compatibility."
else
  mv "$TMP_TEX_INTERMEDIATE" "$TMP_TEX"
fi

# 3) Prefer PNG over PDF in \includegraphics (we created PNGs above)
if [ -d "$FIGDIR" ]; then
  sed -i 's/\\includegraphics\(\[[^]]*\]\)\?{\([^}]*\)\.pdf}/\\includegraphics\1{\2.png}/g' "$TMP_TEX"
fi

# 4) Run Pandoc
echo "==> Running Pandoc → DOCX (citeproc mode: $CITEPROC_MODE)"
pandoc "$TMP_TEX" -o "$OUTDOCX" "${PANDOC_OPTS[@]}"

echo "==> Done."
echo "Created: $OUTDOCX"
echo ""
echo "IMPORTANT: Please verify ASCE formatting compliance:"
echo "  1. Open the DOCX file in Microsoft Word"
echo "  2. Check font: Times New Roman, 12pt throughout"
echo "  3. Check margins: 1 inch on all sides (Layout → Margins)"
echo "  4. Check spacing: Single-spaced (Home → Paragraph)"
echo "  5. Check page numbers: Footer only, no header"
echo "  6. Check figures: Captions below figures"
echo "  7. Check references: Author-date format (Author Year)"
echo ""
echo "For detailed verification checklist, see:"
echo "  $ROOT/final_manuscript/ASCE_FORMATTING_GUIDE.md"
