# AutoSelf Architecture Diagram Generation

## Overview

The AutoSelf architecture diagram is generated from a Mermaid diagram source using Docker/Podman.

## Files

- `figures/autoself_architecture.mmd` - Mermaid diagram source
- `scripts/render_mermaid_architecture.sh` - Rendering script
- `final_manuscript/figures/autoself_architecture.png` - Generated output (300 DPI)
- `final_manuscript/figures/autoself_architecture.pdf` - Generated PDF

## Requirements

**One of the following:**
- Docker
- Podman

## Usage

### Automatic (via generate_all_figures.sh)

```bash
./generate_all_figures.sh
```

This will automatically generate the architecture diagram as step [5.5/6].

### Manual

```bash
bash scripts/render_mermaid_architecture.sh
```

## What the Script Does

1. Uses `ghcr.io/mermaid-js/mermaid-cli:latest` container
2. Renders Mermaid diagram to:
   - PNG (300 DPI, white background)
   - PDF (vector, for LaTeX)
   - SVG (for documentation)
3. Copies PNG and PDF to `final_manuscript/figures/`

## Troubleshooting

### "ERROR: neither podman nor docker found"

Install Docker or Podman:

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install docker.io
sudo systemctl start docker
```

**RHEL/Fedora:**
```bash
sudo dnf install podman
```

**macOS:**
```bash
brew install docker
```

### Alternative: Node.js + mermaid-cli

If you have Node.js installed:

```bash
npm install -g @mermaid-js/mermaid-cli
mmdc -i figures/autoself_architecture.mmd -o figures/autoself_architecture.png -s 2 -b white
mmdc -i figures/autoself_architecture.mmd -o figures/autoself_architecture.pdf -b white
cp figures/autoself_architecture.{png,pdf} final_manuscript/figures/
```

**Note:** mermaid-cli requires Chrome/Chromium for Puppeteer. On WSL/Linux:

```bash
sudo apt install chromium-browser
# OR set environment variable:
export PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser
```

If Chrome/Chromium installation fails, use Docker/Podman instead (see above).

## Diagram Structure

The Mermaid diagram shows:
- User → Frontend (Next.js + React)
- Backend (FastAPI)
- Central Orchestrator
- 4 Robotic Agents (3D Printer, Assembly, Transport, Inspection)
- Verification/Correction Modules
- Data Management Layer (DB, Vector DB, Knowledge Graph, Logs)
- Security & Compliance
- Containerization (Podman/Docker)

## Editing the Diagram

1. Edit `figures/autoself_architecture.mmd`
2. Run `bash scripts/render_mermaid_architecture.sh`
3. Check output in `final_manuscript/figures/`

## Integration with LaTeX

The LaTeX manuscript includes the diagram via:

```latex
\includegraphics[width=0.98\linewidth]{figures/autoself_architecture.png}
```

The PDF version is also generated for high-quality print output.
