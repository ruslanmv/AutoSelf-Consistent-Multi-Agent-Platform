#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# purge.sh
#
# Stops all running Docker containers, removes all containers, and purges
# all Docker images from the host.
# -----------------------------------------------------------------------------

# Ensure docker is installed
if ! command -v docker &> /dev/null; then
  echo "Error: docker not found in PATH. Please install Docker first." >&2
  exit 1
fi

echo "==> Stopping all running containers..."
running_containers=$(docker ps -q)
if [ -n "$running_containers" ]; then
  docker stop $running_containers
else
  echo "No running containers to stop."
fi

echo "==> Removing all containers..."
all_containers=$(docker ps -aq)
if [ -n "$all_containers" ]; then
  docker rm -f $all_containers
else
  echo "No containers to remove."
fi

echo "==> Removing all images..."
all_images=$(docker images -aq)
if [ -n "$all_images" ]; then
  docker rmi -f $all_images
else
  echo "No images to remove."
fi

echo "==> Pruning unused data (networks, volumes, build cache)..."
# The -a flag also removes dangling and unreferenced images, volumes, etc.
docker system prune -a --volumes --force

echo "✅ All Docker images (and unused containers/volumes) have been purged."
