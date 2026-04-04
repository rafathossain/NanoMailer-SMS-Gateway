#!/bin/bash

echo "Collect static files"
uv run python manage.py collectstatic --noinput

echo "Applying database migrations"
uv run python manage.py migrate --noinput

echo "Removing stale content types"
uv run python manage.py remove_stale_contenttypes --include-stale-apps --no-input 2>/dev/null || true

echo "Starting server"
uv run hypercorn config.asgi:application --bind 0.0.0.0:8001 --workers 2
