# scripts/reproduce.sh
#!/usr/bin/env bash
set -euo pipefail

# -------------------------
# One-click reproduction script
# - Runs both experiments across all seeds/p-values (CI reduces scope)
# - Writes CSVs to results/, figures to figs/, and copies key figs to manuscript_results/
# -------------------------

# Env-configurable paths
RESULTS_DIR="${AUTOSELF_RESULTS_DIR:-results}"
FIGS_DIR="${AUTOSELF_FIGS_DIR:-figs}"
CONFIG_DIR="${AUTOSELF_CONFIG_DIR:-configs}"
SEEDS_FILE="${AUTOSELF_SEEDS_FILE:-seeds.yaml}"
MANUSCRIPT_DIR="${AUTOSELF_MANUSCRIPT_DIR:-manuscript_results}"

# Flags
CI_MODE="${CI_MODE:-0}"     # if 1 => reduced seeds
LLM="${LLM:-off}"           # on|off
PYTHON_BIN="${PYTHON_BIN:-python}"

mkdir -p "$RESULTS_DIR" "$FIGS_DIR" "$MANUSCRIPT_DIR"

echo "== AutoSelf Reproduction =="
echo "RESULTS_DIR:      $RESULTS_DIR"
echo "FIGS_DIR:         $FIGS_DIR"
echo "MANUSCRIPT_DIR:   $MANUSCRIPT_DIR"
echo "CONFIG_DIR:       $CONFIG_DIR"
echo "SEEDS_FILE:       $SEEDS_FILE"
echo "LLM:              $LLM"
echo "CI_MODE:          $CI_MODE"
echo "PYTHON:           $PYTHON_BIN"
echo "------------------------------------------"

# 1) Hazards/Failures (first_experiment.py)
echo "[1/4] Running Experiment 1 (Hazards/Failures)…"
if [ "$CI_MODE" = "1" ]; then
  # Reduced seeds; use seed-offset=0 and run a single loop
  $PYTHON_BIN first_experiment.py \
    --config-dir "$CONFIG_DIR" \
    --seeds "$SEEDS_FILE" \
    --only all \
    --mode full \
    --llm "$LLM" \
    --seed-offset 0
else
  # Full seeds (as declared in seeds.yaml)
  $PYTHON_BIN first_experiment.py \
    --config-dir "$CONFIG_DIR" \
    --seeds "$SEEDS_FILE" \
    --only all \
    --mode full \
    --llm "$LLM"
fi

# 2) Contention (second_experiment.py) with ablations
echo "[2/4] Running Experiment 2 (Contention)…"
if [ "$CI_MODE" = "1" ]; then
  # Reduced seeds and limited p-grid via override
  $PYTHON_BIN second_experiment.py \
    --config-dir "$CONFIG_DIR" \
    --seeds "$SEEDS_FILE" \
    --tasks 10 \
    --mode full \
    --llm "$LLM" \
    --p-override 0.1 0.5 0.9
else
  # Full grid from config
  $PYTHON_BIN second_experiment.py \
    --config-dir "$CONFIG_DIR" \
    --seeds "$SEEDS_FILE" \
    --tasks 15 \
    --mode full \
    --llm "$LLM"
  $PYTHON_BIN second_experiment.py \
    --config-dir "$CONFIG_DIR" \
    --seeds "$SEEDS_FILE" \
    --tasks 15 \
    --mode rules-only \
    --llm "$LLM"
  $PYTHON_BIN second_experiment.py \
    --config-dir "$CONFIG_DIR" \
    --seeds "$SEEDS_FILE" \
    --tasks 15 \
    --mode sim-only \
    --llm "$LLM"
fi

# 3) Aggregation (medians + CI to JSON summaries)
echo "[3/4] Aggregating results…"
$PYTHON_BIN scripts/aggregate.py --results "$RESULTS_DIR"

# 4) Figures and LaTeX exports
echo "[4/4] Generating plots…"
$PYTHON_BIN scripts/plot_throughput.py --results "$RESULTS_DIR" --figs "$FIGS_DIR"
$PYTHON_BIN scripts/plot_timelines.py --results "$RESULTS_DIR" --figs "$FIGS_DIR"

echo "Exporting LaTeX macros…"
$PYTHON_BIN scripts/export_for_latex.py --results "$RESULTS_DIR" --out "$RESULTS_DIR/latex_values.tex"

# Copy key figures to manuscript_results/
cp -f "$FIGS_DIR/throughput_plot.pdf" "$MANUSCRIPT_DIR/" 2>/dev/null || true
cp -f "$FIGS_DIR/Nominal_Mission_timeline.png" "$MANUSCRIPT_DIR/" 2>/dev/null || true
cp -f "$FIGS_DIR/Dust_Storm_Hazard_timeline.png" "$MANUSCRIPT_DIR/" 2>/dev/null || true
cp -f "$FIGS_DIR/Nozzle_Clog_Failure_timeline.png" "$MANUSCRIPT_DIR/" 2>/dev/null || true

echo "✅ Reproduction complete."
echo "Artifacts:"
echo " - CSVs:    $RESULTS_DIR"
echo " - Figures: $FIGS_DIR"
echo " - Manuscript picks: $MANUSCRIPT_DIR"
