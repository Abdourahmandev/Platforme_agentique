#!/bin/sh
# First-start initialisation of Dorasso's accounting database (runs once, from
# /docker-entrypoint-initdb.d, as the postgres superuser). Creates the schemas
# and four least-privilege roles; passwords come from Docker secrets files.
#
#   ledger_migrator : owns both schemas, runs migrations (no superuser).
#   ledger_engine   : the accounting engine; reads and writes ledger and essai.
#   ledger_essai    : dry-run (phase 4); writes essai only, cannot write ledger.
#   ledger_dorasso  : Dorasso itself; read-only on both schemas.
set -eu

pw() { tr -d '\r\n' < "/run/secrets/$1"; }

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v migrator="$(pw ledger_migrator_password)" -v engine="$(pw ledger_engine_password)" \
  -v essai="$(pw ledger_essai_password)" -v dorasso="$(pw ledger_dorasso_password)" <<'SQL'
REVOKE ALL ON DATABASE comptabilite FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

CREATE ROLE ledger_migrator LOGIN PASSWORD :'migrator' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE ledger_engine   LOGIN PASSWORD :'engine'   NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE ledger_essai    LOGIN PASSWORD :'essai'    NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE ledger_dorasso  LOGIN PASSWORD :'dorasso'  NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE comptabilite TO ledger_migrator, ledger_engine, ledger_essai, ledger_dorasso;

CREATE SCHEMA ledger AUTHORIZATION ledger_migrator;
CREATE SCHEMA essai  AUTHORIZATION ledger_migrator;

-- Usage of each schema.
GRANT USAGE ON SCHEMA ledger TO ledger_engine, ledger_dorasso;
GRANT USAGE ON SCHEMA essai  TO ledger_engine, ledger_essai, ledger_dorasso;

-- Privileges on every table and sequence the migrator creates later.
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
