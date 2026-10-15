#!/usr/bin/env bash
# Minimal SQL migration runner for migrations/NNN_*.sql.
#
#   migrate.sh status     list applied / pending files
#   migrate.sh baseline   mark every file as applied WITHOUT running it
#                         (use once on a database that was set up by hand)
#   migrate.sh apply      run pending files in order inside a transaction each
#
# Requires DATABASE_URL in the environment (asyncpg form is accepted and
# converted) and psql on PATH.
set -euo pipefail

MIGRATIONS_DIR="${MIGRATIONS_DIR:-$(cd "$(dirname "$0")/../migrations" && pwd)}"
: "${DATABASE_URL:?DATABASE_URL is required}"

# postgresql+asyncpg://...?ssl=require  ->  postgresql://...?sslmode=require
PSQL_URL="${DATABASE_URL/postgresql+asyncpg:\/\//postgresql://}"
PSQL_URL="${PSQL_URL/ssl=require/sslmode=require}"

psqlq() { psql "$PSQL_URL" -v ON_ERROR_STOP=1 -X -q -t -A "$@"; }

ensure_table() {
  psqlq -c "CREATE TABLE IF NOT EXISTS schema_migrations (
              filename   TEXT PRIMARY KEY,
              applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );"
}

list_files() {
  # Only numbered migration files; backups/dumps in the same folder are ignored.
  find "$MIGRATIONS_DIR" -maxdepth 1 -type f -name '[0-9][0-9][0-9]_*.sql' -printf '%f\n' | sort
}

applied() { psqlq -c "SELECT filename FROM schema_migrations ORDER BY filename;"; }

pending() {
  comm -23 <(list_files) <(applied)
}

cmd="${1:-status}"
ensure_table

case "$cmd" in
  status)
    echo "Applied:"; applied | sed 's/^/  /'
    echo "Pending:"; pending | sed 's/^/  /'
    ;;
  baseline)
    for f in $(pending); do
      psqlq -c "INSERT INTO schema_migrations (filename) VALUES ('$f') ON CONFLICT DO NOTHING;"
      echo "baselined $f"
    done
    ;;
  apply)
    for f in $(pending); do
      echo "applying $f"
      # Each file runs in its own transaction; a failure stops the deploy.
      psql "$PSQL_URL" -v ON_ERROR_STOP=1 -X -q --single-transaction -f "$MIGRATIONS_DIR/$f"
      psqlq -c "INSERT INTO schema_migrations (filename) VALUES ('$f');"
    done
    echo "migrations up to date"
    ;;
  *)
    echo "usage: $0 {status|baseline|apply}" >&2; exit 2 ;;
esac
