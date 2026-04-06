#!/bin/bash
# ==============================================================================
# generate_all_figures.sh
#
# Generates all publication-quality figures for AutoSelf manuscript submission
# ASCE Earth & Space 2026 - Submission #87
#
# Usage: ./generate_all_figures.sh
#
# Requirements:
# - Python 3.11+
# - All dependencies installed (matplotlib, pandas, numpy, scipy)
# - Experiment data in results/ directory
#
# Outputs:
# - 9 figures (PDF + PNG at 300 DPI) in final_manuscript/figures/
# ==============================================================================

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Banner
echo ""
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║         AutoSelf Manuscript Figure Generation Script                  ║"
echo "║         ASCE Earth & Space 2026 - Submission #87                      ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""

# Change to project root
cd "$(dirname "$0")"

# Verify we're in the right directory
if [ ! -f "paper_artifacts_exp1.py" ] || [ ! -f "paper_artifacts_exp3.py" ]; then
    echo -e "${RED}✗ ERROR: Script files not found. Are you in the project root?${NC}"
    exit 1
fi

# Check if results directory exists
if [ ! -d "results" ]; then
    echo -e "${RED}✗ ERROR: results/ directory not found${NC}"
    echo "  Please run experiments first to generate data"
    exit 1
fi

# Check for required data files
echo -e "${BLUE}[1/6] Verifying experiment data...${NC}"
REQUIRED_FILES=(
    "results/makespan.csv"
    "results/conflicts.csv"
    "results/overhead.csv"
    "results/timeline_nominal.csv"
    "results/timeline_hazard.csv"
    "results/timeline_failure.csv"
)

MISSING_FILES=0
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${YELLOW}  ⚠ Missing: $file${NC}"
        MISSING_FILES=$((MISSING_FILES + 1))
    else
        echo -e "${GREEN}  ✓ Found: $file${NC}"
    fi
done

if [ $MISSING_FILES -gt 0 ]; then
    echo -e "${RED}✗ ERROR: $MISSING_FILES required data file(s) missing${NC}"
    echo "  Please run experiments first:"
    echo "    python first_experiment.py --mode full --llm off"
    echo "    python third_experiment.py"
    exit 1
fi

echo -e "${GREEN}✓ All required data files present${NC}"
echo ""

# Generate Experiment 3 plots (4-5 figures)
echo -e "${BLUE}[2/6] Generating Experiment 3 plots (throughput, makespan, conflicts, overhead)...${NC}"
if python paper_artifacts_exp3.py; then
    echo -e "${GREEN}✓ Experiment 3 plots generated successfully${NC}"
else
    echo -e "${RED}✗ ERROR: Failed to generate Experiment 3 plots${NC}"
    exit 1
fi
echo ""

# Generate timeline plots (3 figures)
echo -e "${BLUE}[3/6] Generating timeline plots (nominal, dust storm, nozzle clog)...${NC}"
if python paper_artifacts_exp1.py; then
    echo -e "${GREEN}✓ Timeline plots generated successfully${NC}"
else
    echo -e "${RED}✗ ERROR: Failed to generate timeline plots${NC}"
    exit 1
fi
echo ""

# Copy and rename figures to final manuscript folder
echo -e "${BLUE}[4/6] Organizing and renaming figures for manuscript submission...${NC}"

# Create figures directory
mkdir -p final_manuscript/figures
mkdir -p manuscript_results  # Ensure this exists

# Function to copy and rename files (handles colons in filenames)
copy_and_rename() {
    local source="$1"
    local dest="$2"

    if [ -f "$source" ]; then
        cp "$source" "$dest"
        echo -e "${GREEN}  ✓ Copied: $(basename "$dest")${NC}"
        return 0
    else
        echo -e "${YELLOW}  ⚠ Not found: $source${NC}"
        return 1
    fi
}

# Copy Experiment 3 plots (try both manuscript_results and results directories)
echo -e "${BLUE}  Copying Experiment 3 plots...${NC}"
for plot in throughput makespan conflicts overhead; do
    # Try manuscript_results first
    if [ -f "manuscript_results/exp3_${plot}_plot.pdf" ]; then
        cp "manuscript_results/exp3_${plot}_plot.pdf" "final_manuscript/figures/"
        cp "manuscript_results/exp3_${plot}_plot.png" "final_manuscript/figures/" 2>/dev/null || true
        echo -e "${GREEN}  ✓ exp3_${plot}_plot.pdf${NC}"
    # Fallback to results directory
    elif [ -f "results/exp3_${plot}_plot.pdf" ]; then
        cp "results/exp3_${plot}_plot.pdf" "final_manuscript/figures/"
        cp "results/exp3_${plot}_plot.png" "final_manuscript/figures/" 2>/dev/null || true
        echo -e "${GREEN}  ✓ exp3_${plot}_plot.pdf (from results/)${NC}"
    else
        echo -e "${YELLOW}  ⚠ Missing: exp3_${plot}_plot.pdf${NC}"
    fi
done

# Copy and rename timeline plots (handle colons in filenames)
echo -e "${BLUE}  Copying and renaming timeline plots...${NC}"

# Timeline: nominal
copy_and_rename "manuscript_results/Mission_timeline:_nominal.pdf" \
                "final_manuscript/figures/Mission_timeline_nominal.pdf" || \
copy_and_rename "manuscript_results/Mission_timeline_nominal.pdf" \
                "final_manuscript/figures/Mission_timeline_nominal.pdf"

copy_and_rename "manuscript_results/Mission_timeline:_nominal.png" \
                "final_manuscript/figures/Mission_timeline_nominal.png" 2>/dev/null || true

# Timeline: dust-storm hazard
copy_and_rename "manuscript_results/Mission_timeline:_dust-storm_hazard.pdf" \
                "final_manuscript/figures/Mission_timeline_dust-storm_hazard.pdf" || \
copy_and_rename "manuscript_results/Mission_timeline_dust-storm_hazard.pdf" \
                "final_manuscript/figures/Mission_timeline_dust-storm_hazard.pdf"

copy_and_rename "manuscript_results/Mission_timeline:_dust-storm_hazard.png" \
                "final_manuscript/figures/Mission_timeline_dust-storm_hazard.png" 2>/dev/null || true

# Timeline: nozzle-clog failure
copy_and_rename "manuscript_results/Mission_timeline:_nozzle-clog_failure.pdf" \
                "final_manuscript/figures/Mission_timeline_nozzle-clog_failure.pdf" || \
copy_and_rename "manuscript_results/Mission_timeline_nozzle-clog_failure.pdf" \
                "final_manuscript/figures/Mission_timeline_nozzle-clog_failure.pdf"

copy_and_rename "manuscript_results/Mission_timeline:_nozzle-clog_failure.png" \
                "final_manuscript/figures/Mission_timeline_nozzle-clog_failure.png" 2>/dev/null || true

# Copy architecture diagram
echo -e "${BLUE}  Checking for architecture diagram...${NC}"
if [ -f "autoself_architecture.png" ]; then
    cp autoself_architecture.png final_manuscript/figures/
    echo -e "${GREEN}  ✓ Copied architecture diagram${NC}"
elif [ -f "assets/autoself_architecture.png" ]; then
    cp assets/autoself_architecture.png final_manuscript/figures/
    echo -e "${GREEN}  ✓ Copied architecture diagram (from assets/)${NC}"
else
    echo -e "${YELLOW}  ⚠ Architecture diagram not found (autoself_architecture.png)${NC}"
    echo "    This file may need to be created separately"
fi

echo -e "${GREEN}✓ Figures organized in final_manuscript/figures/${NC}"
echo ""

# Generate ablation plot from existing CSVs (no re-run)
echo -e "${BLUE}[5/6] Generating Experiment 3 ablation plot (from existing results)...${NC}"
mkdir -p figures

if python scripts/make_exp3_ablation_from_results.py \
    --in results/makespan.csv \
    --outdir manuscript_results \
    --tasks-per-run 6 \
    --save-png; then

    if [ -f "manuscript_results/exp3_ablation_plot.pdf" ]; then
        cp manuscript_results/exp3_ablation_plot.pdf final_manuscript/figures/
        cp manuscript_results/exp3_ablation_plot.pdf figures/
        [ -f "manuscript_results/exp3_ablation_plot.png" ] && \
            cp manuscript_results/exp3_ablation_plot.png final_manuscript/figures/ && \
            cp manuscript_results/exp3_ablation_plot.png figures/
        echo -e "${GREEN}✓ Ablation plot generated and copied${NC}"
    else
        echo -e "${RED}✗ ERROR: exp3_ablation_plot.pdf not found after generation${NC}"
        exit 1
    fi
else
    echo -e "${RED}✗ ERROR: Failed to generate ablation plot${NC}"
    exit 1
fi
echo ""

# Generate architecture diagram from Mermaid
echo -e "${BLUE}[5.5/6] Generating AutoSelf architecture diagram from Mermaid...${NC}"
if [ ! -f "final_manuscript/figures/autoself_architecture.png" ]; then
    if [ -f "scripts/render_mermaid_architecture.sh" ]; then
        if bash scripts/render_mermaid_architecture.sh; then
            echo -e "${GREEN}✓ Architecture diagram generated from Mermaid${NC}"
        else
            echo -e "${RED}✗ ERROR: Failed to generate architecture diagram${NC}"
            echo -e "${YELLOW}  Make sure Docker or Podman is installed and running${NC}"
            echo -e "${YELLOW}  Or install mermaid-cli: npm install -g @mermaid-js/mermaid-cli${NC}"
            exit 1
        fi
    else
        echo -e "${RED}✗ ERROR: scripts/render_mermaid_architecture.sh not found${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ Architecture diagram already exists${NC}"
fi
echo ""

# Verify all figures are present
echo -e "${BLUE}[6/6] Verifying generated figures...${NC}"

# Core required figures (8 minimum)
REQUIRED_FIGURES=(
    "Mission_timeline_dust-storm_hazard.pdf"
    "Mission_timeline_nozzle-clog_failure.pdf"
    "Mission_timeline_nominal.pdf"
    "exp3_throughput_plot.pdf"
    "exp3_makespan_plot.pdf"
    "exp3_conflicts_plot.pdf"
    "exp3_overhead_plot.pdf"
    "exp3_ablation_plot.pdf"
)

# Optional figures
OPTIONAL_FIGURES=(
    "autoself_architecture.png"
)

MISSING_REQUIRED=0
PRESENT_FIGS=0
TOTAL_PRESENT=0

echo -e "${BLUE}Required figures:${NC}"
for fig in "${REQUIRED_FIGURES[@]}"; do
    if [ -f "final_manuscript/figures/$fig" ]; then
        echo -e "${GREEN}  ✓ $fig${NC}"
        PRESENT_FIGS=$((PRESENT_FIGS + 1))
        TOTAL_PRESENT=$((TOTAL_PRESENT + 1))
    else
        echo -e "${RED}  ✗ MISSING: $fig${NC}"
        MISSING_REQUIRED=$((MISSING_REQUIRED + 1))
    fi
done

echo -e "${BLUE}Optional figures:${NC}"
for fig in "${OPTIONAL_FIGURES[@]}"; do
    if [ -f "final_manuscript/figures/$fig" ]; then
        echo -e "${GREEN}  ✓ $fig${NC}"
        TOTAL_PRESENT=$((TOTAL_PRESENT + 1))
    else
        echo -e "${YELLOW}  ○ Not present: $fig (optional)${NC}"
    fi
done

echo ""
echo "════════════════════════════════════════════════════════════════════════"

if [ $MISSING_REQUIRED -eq 0 ]; then
    echo -e "${GREEN}✓ SUCCESS! All required figures generated and ready for submission${NC}"
    echo ""
    echo "Figures present: ${TOTAL_PRESENT}"
    echo "  - 8 required plots: ✓"
    echo "  - Architecture diagram: $([ -f 'final_manuscript/figures/autoself_architecture.png' ] && echo '✓' || echo '○ (create separately)')"
    echo ""
    echo "Location: final_manuscript/figures/"
    echo ""
    echo "Generated files:"
    ls -lh final_manuscript/figures/ | grep -E '\.(pdf|png)$' | awk '{printf "  %s (%s)\n", $9, $5}'
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "NEXT STEPS:"
    echo "═══════════════════════════════════════════════════════════════"
    echo "1. If architecture diagram is missing, create/copy it manually:"
    echo "   cp path/to/autoself_architecture.png final_manuscript/figures/"
    echo ""
    echo "2. Compile manuscript:"
    echo "   cd final_manuscript"
    echo "   pdflatex final_manuscript.tex"
    echo "   pdflatex final_manuscript.tex"
    echo "   pdflatex final_manuscript.tex"
    echo ""
    echo "3. Convert to DOCX for ASCE submission:"
    echo "   pandoc final_manuscript.tex -o final_manuscript.docx"
    echo ""
    echo "4. Upload to TEES system:"
    echo "   https://na.eventscloud.com/eSites/830339/Login"
    echo ""
    exit 0
else
    echo -e "${RED}✗ ERROR: $MISSING_REQUIRED required figures are missing${NC}"
    echo ""
    echo "Present: $PRESENT_FIGS of 8 required figures"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check that experiments ran successfully"
    echo "  2. Look for error messages in the output above"
    echo "  3. Verify data files exist in results/"
    echo "  4. Check manuscript_results/ for generated plots"
    echo ""
    exit 1
fi
