# Makefile — AutoSelf Repro + Backend/Frontend + Paper Artifacts
#
# Usage:
#   make help                 # list all targets
#   make install              # create venv and install all Python deps
#   make run                  # run FastAPI backend + Flask frontend locally
#   make stop                 # stop the local backend and frontend servers
#   make reproduce            # run full paper pipeline (results + figs + latex)
#   make aggregate plots      # aggregate CSVs and refresh figures only
#   make docker-build-all     # build backend & frontend images
#   make docker-run-backend   # run backend container on :8008
#   make docker-run-frontend  # run frontend container on :5000 (needs SERVER_URL)
#   make clean                # remove caches; see also clean-results / clean-figs

# -----------------------------
# Variables
# -----------------------------
SHELL := /bin/bash
PY?=python3.11
VENV?=.venv
PYBIN:=$(VENV)/bin/python
PIP:=$(VENV)/bin/pip

# Artifact dirs (override via env if needed)
RESULTS_DIR?=results
FIGS_DIR?=figs
CONFIG_DIR?=configs
MANUSCRIPT_DIR?=manuscript_results

# Docker
BACKEND_IMG?=autoself-backend:latest
FRONTEND_IMG?=autoself-frontend:latest
SERVER_PORT?=8008
CLIENT_PORT?=5000
SERVER_URL?=http://localhost:$(SERVER_PORT)

# CI toggle (reduced seeds)
CI?=0

# -----------------------------
# Helpers
# -----------------------------
.PHONY: help
help: ## Show this help
	@echo "\nAutoSelf — common tasks"; \
	echo; \
	awk 'BEGIN {FS = ":.*##"; printf "%-28s %s\n", "Target", "Description"} /^[a-zA-Z0-9_\-]+:.*##/ {printf "%-28s %s\n", $$1, $$2}' $(MAKEFILE_LIST); \
	echo; \
	echo "Variables you can override:"; \
	echo "  PY=$(PY)  VENV=$(VENV)  RESULTS_DIR=$(RESULTS_DIR)  FIGS_DIR=$(FIGS_DIR)"; \
	echo "  BACKEND_IMG=$(BACKEND_IMG)  FRONTEND_IMG=$(FRONTEND_IMG)"; \
	echo

# -----------------------------
# Environment / deps
# -----------------------------
.PHONY: venv
venv: ## Create Python venv (Python 3.11 recommended)
	@if [ ! -d "$(VENV)" ]; then \
		$(PY) -m venv $(VENV); \
		echo "[venv] created at $(VENV)"; \
	else \
		echo "[venv] exists: $(VENV)"; \
	fi

.PHONY: deps
deps: venv ## Install Python deps from requirements.txt (and optional extras if present)
	@$(PIP) --version >/dev/null 2>&1 || (echo "[err] pip not found in venv" && exit 1)
	@$(PIP) install --upgrade pip wheel
	@if [ -f requirements.txt ]; then \
		echo "[pip] installing requirements.txt"; \
		$(PIP) install -r requirements.txt; \
	else \
		echo "[warn] requirements.txt not found — skipping"; \
	fi
	@if [ -f requirements.backend.txt ]; then \
		echo "[pip] installing requirements.backend.txt"; \
		$(PIP) install -r requirements.backend.txt; \
	fi
	@if [ -f requirements.frontend.txt ]; then \
		echo "[pip] installing requirements.frontend.txt"; \
		$(PIP) install -r requirements.frontend.txt; \
	fi

.PHONY: install
install: deps ## Create venv and install all Python dependencies
	@echo "[install] environment ready."

# -----------------------------
# Local run
# -----------------------------
.PHONY: stop
stop: ## Stop any running backend or frontend servers
	@echo "Stopping servers on ports $(CLIENT_PORT) and $(SERVER_PORT)..."
	@-lsof -t -i:$(CLIENT_PORT) | xargs -r kill -9 >/dev/null 2>&1
	@-lsof -t -i:$(SERVER_PORT) | xargs -r kill -9 >/dev/null 2>&1
	@echo "Servers stopped."

.PHONY: run
run: stop ## Stop existing servers, then run backend (FastAPI) + frontend (Flask)
	@echo "Starting servers..."
	@SERVER_URL=$(SERVER_URL) $(PYBIN) run.py

.PHONY: run-backend
run-backend: ## Run only the FastAPI backend locally
	@$(PYBIN) -c "import uvicorn, os; os.environ.setdefault('SERVER_URL','$(SERVER_URL)'); import server; uvicorn.run(server.app, host='0.0.0.0', port=$(SERVER_PORT))"

.PHONY: run-frontend
run-frontend: ## Run only the Flask frontend locally (requires SERVER_URL to be set)
	@SERVER_URL=$(SERVER_URL) $(PYBIN) -c "from client import app; app.run(host='0.0.0.0', port=$(CLIENT_PORT), debug=False)"

# -----------------------------
# Repro / artifacts
# -----------------------------
.PHONY: reproduce
reproduce: ## One-click reproduction (experiments across seeds / p-grid)
	@chmod +x scripts/reproduce.sh
	@AUTOSELF_RESULTS_DIR=$(RESULTS_DIR) AUTOSELF_CONFIG_DIR=$(CONFIG_DIR) CI=$(CI) bash scripts/reproduce.sh

.PHONY: aggregate
aggregate: ## Aggregate CSVs into summaries (medians, 95% CIs)
	@AUTOSELF_RESULTS_DIR=$(RESULTS_DIR) $(PYBIN) scripts/aggregate.py

.PHONY: plots
plots: plot-throughput plot-timelines ## Generate all figures into $(FIGS_DIR)

.PHONY: plot-throughput
plot-throughput: ## Build throughput figure from results/throughput.csv
	@AUTOSELF_RESULTS_DIR=$(RESULTS_DIR) AUTOSELF_FIGS_DIR=$(FIGS_DIR) $(PYBIN) scripts/plot_throughput.py

.PHONY: plot-timelines
plot-timelines: ## Build timeline figures from timeline_*.csv
	@AUTOSELF_RESULTS_DIR=$(RESULTS_DIR) AUTOSELF_FIGS_DIR=$(FIGS_DIR) $(PYBIN) scripts/plot_timelines.py

.PHONY: export-latex
export-latex: ## Export LaTeX macros (latex_values.tex) from results summaries
	@AUTOSELF_RESULTS_DIR=$(RESULTS_DIR) $(PYBIN) scripts/export_for_latex.py

# -----------------------------
# Docker
# -----------------------------
.PHONY: docker-build-backend
docker-build-backend: ## Build backend image (Dockerfile.backend)
	docker build -f Dockerfile.backend -t $(BACKEND_IMG) .

.PHONY: docker-build-frontend
docker-build-frontend: ## Build frontend image (Dockerfile.frontend)
	docker build -f Dockerfile.frontend -t $(FRONTEND_IMG) .

.PHONY: docker-build-all
docker-build-all: docker-build-backend docker-build-frontend ## Build all images

.PHONY: docker-run-backend
docker-run-backend: ## Run backend container on :$(SERVER_PORT)
	docker run --rm -it -p $(SERVER_PORT):8008 --env-file .env $(BACKEND_IMG)

.PHONY: docker-run-frontend
docker-run-frontend: ## Run frontend container on :$(CLIENT_PORT) (requires SERVER_URL)
	docker run --rm -it -p $(CLIENT_PORT):5000 -e SERVER_URL=$(SERVER_URL) $(FRONTEND_IMG)

# -----------------------------
# Sanity checks and linting (optional)
# -----------------------------
.PHONY: check
check: ## Verify required files exist for paper pipeline
	@for f in first_experiment.py second_experiment.py scripts/reproduce.sh scripts/aggregate.py scripts/plot_throughput.py scripts/plot_timelines.py scripts/export_for_latex.py; do \
		[ -f $$f ] || { echo "[MISSING] $$f"; exit 1; }; \
	done; \
	echo "All required scripts present."

# -----------------------------
# Document generation
# -----------------------------
.PHONY: figures
figures: ## Generate all figures using generate_all_figures.sh
	@bash generate_all_figures.sh

.PHONY: docx
docx: figures ## Generate Word document (DOCX) from LaTeX manuscript
	@bash scripts/make_docx.sh

.PHONY: clean-docx
clean-docx: ## Remove generated DOCX file
	@rm -f final_manuscript/*.docx

# -----------------------------
# Cleaning
# -----------------------------
.PHONY: clean
clean: ## Remove Python caches and build artifacts
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type f -name ".DS_Store" -delete

.PHONY: clean-results
clean-results: ## Remove results/* (CSV & summaries)
	@rm -rf $(RESULTS_DIR)/*

.PHONY: clean-figs
clean-figs: ## Remove figs/* (generated figures)
	@rm -rf $(FIGS_DIR)/*