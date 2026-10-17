#!/bin/sh
# First-start initialisation of Dorasso's accounting database (runs once, from
# /docker-entrypoint-initdb.d, as the postgres user). Creates the schemas and four
# least-privilege roles. Passwords come from Docker secrets prepared by
# prepare-ledger.py (container copies readable by the postgres user only).
#
#   ledger_migrator : owns both schemas, runs migrations (no superuser).
#   ledger_engine   : the accounting engine; reads and writes ledger and essai.
#   ledger_essai    : dry-run (phase 4); essai only, no access at all to ledger.
#   ledger_dorasso  : Dorasso itself; read-only on both schemas.
set -eu

# Read one secret; refuse a missing, empty or unexpected value. Passwords are
# url-safe tokens, so they can be embedded in SQL literals; they never appear in
# a command line (the SQL is sent on stdin).
pw() {
  v=$(tr -d '\r\n' < "/run/secrets/$1") || { echo "secret illisible : $1" >&2; exit 1; }
  case "$v" in
    ''|*[!A-Za-z0-9_-]*) echo "secret vide ou invalide : $1" >&2; exit 1 ;;
  esac
  printf '%s' "$v"
}
MIGRATOR=$(pw ledger_migrator_password)
ENGINE=$(pw ledger_engine_password)
ESSAI=$(pw ledger_essai_password)
DORASSO=$(pw ledger_dorasso_password)

# One transaction: roles and rights are created completely or not at all.
psql -v ON_ERROR_STOP=1 --single-transaction --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
-- No implicit rights for anyone, in any database of this instance.
REVOKE ALL ON DATABASE comptabilite FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE postgres FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE template1 FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

CREATE ROLE ledger_migrator LOGIN PASSWORD '$MIGRATOR' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE ledger_engine   LOGIN PASSWORD '$ENGINE'   NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE ledger_essai    LOGIN PASSWORD '$ESSAI'    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE ledger_dorasso  LOGIN PASSWORD '$DORASSO'  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CONNECT ON DATABASE comptabilite TO ledger_migrator, ledger_engine, ledger_essai, ledger_dorasso;

CREATE SCHEMA ledger AUTHORIZATION ledger_migrator;
CREATE SCHEMA essai  AUTHORIZATION ledger_migrator;

GRANT USAGE ON SCHEMA ledger TO ledger_engine, ledger_dorasso;
GRANT USAGE ON SCHEMA essai  TO ledger_engine, ledger_essai, ledger_dorasso;

-- Future objects created by the migrator. Functions get no implicit EXECUTE
-- (a SECURITY DEFINER function could otherwise bypass these rules): each one
-- must be granted explicitly in its migration.
ALTER DEFAULT PRIVILEGES FOR ROLE ledger_migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE ledger_migrator IN SCHEMA ledger
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ledger_engine;
ALTER DEFAULT PRIVILEGES FOR ROLE ledger_migrator IN SCHEMA ledger
  GRANT SELECT ON TABLES TO ledger_dorasso;
ALTER DEFAULT PRIVILEGES FOR ROLE ledger_migrator IN SCHEMA ledger
  GRANT USAGE, SELECT ON SEQUENCES TO ledger_engine;
ALTER DEFAULT PRIVILEGES FOR ROLE ledger_migrator IN SCHEMA essai
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ledger_engine, ledger_essai;
ALTER DEFAULT PRIVILEGES FOR ROLE ledger_migrator IN SCHEMA essai
  GRANT SELECT ON TABLES TO ledger_dorasso;
ALTER DEFAULT PRIVILEGES FOR ROLE ledger_migrator IN SCHEMA essai
  GRANT USAGE, SELECT ON SEQUENCES TO ledger_engine, ledger_essai;
SQL

# Passwords on every TCP connection, loopback included (POSTGRES_INITDB_ARGS sets
# --auth-host=scram-sha-256). Checked on the rules PostgreSQL actually parsed; the Unix
# socket stays trusted for `docker exec` maintenance, which requires Docker admin rights.
bad=$(psql -X -At --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c \
  "SELECT count(*) FROM pg_hba_file_rules WHERE (type <> 'local' AND auth_method <> 'scram-sha-256') OR error IS NOT NULL")
if [ "$bad" != 0 ]; then echo "pg_hba : $bad regle(s) TCP sans mot de passe ou invalide(s)" >&2; exit 1; fi

# Last step, only after every rule above succeeded: the marker that entrypoint.sh
# requires before PostgreSQL may ever serve this volume.
date -u +%Y-%m-%dT%H:%M:%SZ > "$PGDATA/dorasso-securite-ok"
