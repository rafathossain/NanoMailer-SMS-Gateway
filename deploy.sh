#!/bin/bash

set -e

echo "========================================"
echo "  SMS Gateway - Docker Setup"
echo "========================================"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker and try again."
    exit 1
fi

# Build and start containers
echo ""
echo "[1/3] Building containers..."
docker compose build

echo ""
echo "[2/3] Starting containers..."
docker compose up -d

echo ""
echo "[3/3] Waiting for services to be ready..."
sleep 5

# Check service status
echo ""
echo "========================================"
echo "  Service Status"
echo "========================================"
docker compose ps

echo ""
echo "Useful commands:"
echo "  docker compose logs -f web       # Follow web logs"
echo "  docker compose logs -f celery    # Follow celery logs"
echo "  docker compose down              # Stop all containers"
echo "  docker compose down -v           # Stop and remove volumes"
echo ""
