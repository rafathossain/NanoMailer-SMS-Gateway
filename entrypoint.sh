#!/bin/bash

# Wait for MariaDB
mariadb_ready() {
  uv run python <<END
import sys
import mysql.connector
try:
    mydb = mysql.connector.connect(
        host="${DB_HOST}",
        user="${DB_USER}",
        password="${DB_PASSWORD}",
        port="${DB_PORT:-3306}"
    )
except mysql.connector.OperationalError:
    sys.exit(-1)
sys.exit(0)
END
}

until mariadb_ready; do
  echo >&2 'Waiting for MariaDB...'
  sleep 1
done
echo >&2 'MariaDB is available'

exec "$@"
