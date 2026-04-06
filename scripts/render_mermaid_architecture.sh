#!/usr/bin/env bash
# Render Mermaid diagram to PNG/PDF/SVG
# Tries mermaid-cli (npm) first, then falls back to Docker/Podman

set -e

IN="figures/autoself_architecture.mmd"
OUTDIR="figures"
OUTPNG="${OUTDIR}/autoself_architecture.png"
OUTPDF="${OUTDIR}/autoself_architecture.pdf"
OUTSVG="${OUTDIR}/autoself_architecture.svg"

mkdir -p "${OUTDIR}" final_manuscript/figures

# Check if mermaid-cli (mmdc) is available
if command -v mmdc >/dev/null 2>&1; then
  echo "==> Using mermaid-cli (mmdc) to render diagram..."

  # Render PNG (high-res via scale)
  echo "  - Rendering PNG..."
  mmdc -i "${IN}" -o "${OUTPNG}" -s 2 -b white

  # Render PDF
  echo "  - Rendering PDF..."
  mmdc -i "${IN}" -o "${OUTPDF}" -b white

  # Render SVG
  echo "  - Rendering SVG..."
  mmdc -i "${IN}" -o "${OUTSVG}"

elif command -v npx >/dev/null 2>&1; then
  echo "==> Using mermaid-cli (npx) to render diagram..."

  # Render PNG (high-res via scale)
  echo "  - Rendering PNG..."
  npx -y @mermaid-js/mermaid-cli -i "${IN}" -o "${OUTPNG}" -s 2 -b white 2>&1 | grep -v "npm warn deprecated" || true

  if [ ! -f "${OUTPNG}" ]; then
    echo "ERROR: mermaid-cli failed to generate PNG"
    echo "This may be due to missing Chrome/Chromium for Puppeteer."
    echo "On WSL/Linux, you may need to:"
    echo "  1. Install chromium: apt install chromium-browser"
    echo "  2. Or use Docker/Podman rendering instead"
    echo "  3. Or set PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=false"
    exit 1
  fi

  # Render PDF
  echo "  - Rendering PDF..."
  npx -y @mermaid-js/mermaid-cli -i "${IN}" -o "${OUTPDF}" -b white 2>&1 | grep -v "npm warn deprecated" || true

  # Render SVG
  echo "  - Rendering SVG..."
  npx -y @mermaid-js/mermaid-cli -i "${IN}" -o "${OUTSVG}" 2>&1 | grep -v "npm warn deprecated" || true

elif command -v podman >/dev/null 2>&1; then
  echo "==> Using Podman to render diagram..."
  RUNTIME="podman"
  IMG="ghcr.io/mermaid-js/mermaid-cli:latest"

  # Render PNG
  echo "  - Rendering PNG..."
  $RUNTIME run --rm -u "$(id -u):$(id -g)" \
    -v "$PWD:/data" \
    "$IMG" \
    -i "/data/${IN}" \
    -o "/data/${OUTPNG}" \
    -t default \
    -s 2 \
    -b white

  # Render PDF
  echo "  - Rendering PDF..."
  $RUNTIME run --rm -u "$(id -u):$(id -g)" \
    -v "$PWD:/data" \
    "$IMG" \
    -i "/data/${IN}" \
    -o "/data/${OUTPDF}" \
    -t default \
    -b white

  # Render SVG
  echo "  - Rendering SVG..."
  $RUNTIME run --rm -u "$(id -u):$(id -g)" \
    -v "$PWD:/data" \
    "$IMG" \
    -i "/data/${IN}" \
    -o "/data/${OUTSVG}" \
    -t default

elif command -v docker >/dev/null 2>&1; then
  echo "==> Using Docker to render diagram..."
  RUNTIME="docker"
  IMG="ghcr.io/mermaid-js/mermaid-cli:latest"

  # Render PNG
  echo "  - Rendering PNG..."
  $RUNTIME run --rm -u "$(id -u):$(id -g)" \
    -v "$PWD:/data" \
    "$IMG" \
    -i "/data/${IN}" \
    -o "/data/${OUTPNG}" \
    -t default \
    -s 2 \
    -b white

  # Render PDF
  echo "  - Rendering PDF..."
  $RUNTIME run --rm -u "$(id -u):$(id -g)" \
    -v "$PWD:/data" \
    "$IMG" \
    -i "/data/${IN}" \
    -o "/data/${OUTPDF}" \
    -t default \
    -b white

  # Render SVG
  echo "  - Rendering SVG..."
  $RUNTIME run --rm -u "$(id -u):$(id -g)" \
    -v "$PWD:/data" \
    "$IMG" \
    -i "/data/${IN}" \
    -o "/data/${OUTSVG}" \
    -t default

else
  echo "ERROR: No rendering tool found."
  echo "Please install one of:"
  echo "  - npm install -g @mermaid-js/mermaid-cli"
  echo "  - docker"
  echo "  - podman"
  exit 1
fi

# Copy into manuscript figures folder
cp -f "${OUTPNG}" final_manuscript/figures/autoself_architecture.png
cp -f "${OUTPDF}" final_manuscript/figures/autoself_architecture.pdf

echo "==> Done!"
echo "Generated:"
echo "  ${OUTPNG}"
echo "  ${OUTPDF}"
echo "  ${OUTSVG}"
echo "Copied to:"
echo "  final_manuscript/figures/autoself_architecture.png"
echo "  final_manuscript/figures/autoself_architecture.pdf"
