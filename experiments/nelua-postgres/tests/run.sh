#!/usr/bin/env bash
# The caller selects an existing PostgreSQL test server through libpq PG* vars.
# No application database is reset: create and drop our own isolated database.
set -euo pipefail
cd "$(dirname "$0")/.."
db="nc_test_$$"
createdb "$db"
cleanup() { dropdb --if-exists --force "$db"; }
trap cleanup EXIT
export DATABASE_URL="dbname=$db"
psql -X -v ON_ERROR_STOP=1 -d "$DATABASE_URL" -c 'CREATE EXTENSION nelua_conduit'
python3 tests/integration.py
if [ "${1:-}" = --benchmark ]; then
  python3 tools/benchmark.py --output results/benchmark.md
fi
