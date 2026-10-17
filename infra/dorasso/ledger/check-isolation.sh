#!/usr/bin/env bash
# Prove the least-privilege rules of Dorasso's accounting database on the running
# container. A probe schema object pair with a random suffix is created by the
# migrator and always removed (trap). A refusal counts only if PostgreSQL answers
# SQLSTATE 42501 (insufficient privilege); any other error fails the check.
# Limits: connections are made inside the container (loopback); network isolation
# is checked separately with `docker network inspect` (no host port, internal network).
set -uo pipefail
C=${LEDGER_CONTAINER:-dorasso-ledger-1}
DIR="${LOCALAPPDATA:-$HOME/.local/share}/Dorasso/ledger"
SUFFIX=$(head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n')
T="probe_isolation_$SUFFIX"
fail=0

# run ROLE DATABASE SQL -> prints "ok" or the SQLSTATE of the error.
run() {
  local out
  # The password goes through the environment, never on the docker command line.
  out=$(PGPASSWORD="$(cat "$DIR/$1.password")" docker exec -i -e PGPASSWORD "$C" \
    psql -X -q -v ON_ERROR_STOP=1 -v VERBOSITY=verbose -h 127.0.0.1 -U "$1" -d "$2" -c "$3" 2>&1 >/dev/null)
  if [ $? -eq 0 ]; then echo ok; else sqlstate "$out"; fi
}
# SQLSTATE of an error. Connection failures carry no SQLSTATE in psql output,
# so their two exact messages are mapped to their documented codes.
sqlstate() {
  case "$1" in
    *"permission denied for database"*) echo 42501 ;;
    *"password authentication failed"*) echo 28P01 ;;
    *) echo "$1" | grep -oE '(ERROR|FATAL): +[0-9A-Z]{5}' | head -1 | grep -oE '[0-9A-Z]{5}$' || echo erreur ;;
  esac
}
expect() { # description, expected (ok|42501|28P01), role, database, sql
  local got
  got=$(run "$3" "$4" "$5")
  if [ "$got" = "$2" ]; then echo "ok    $1"; else echo "ECHEC $1 (attendu $2, obtenu $got)"; fail=1; fi
}
# Superuser through the container socket, so that a probe object wrongly created by
# any role (for instance in public) is removed too; then nothing may remain.
admin() { docker exec -i "$C" psql -X -q -At -v ON_ERROR_STOP=1 -U postgres -d comptabilite -c "$1" </dev/null; }
cleanup() {
  admin "SET client_min_messages = warning; DROP TABLE IF EXISTS ledger.$T, essai.$T, ledger.ddl_$SUFFIX, essai.ddl_$SUFFIX, public.ddl_$SUFFIX" >/dev/null \
    || { echo "ECHEC nettoyage des objets de test"; exit 1; }
  [ "$(admin "SELECT count(*) FROM pg_class WHERE relname LIKE '%$SUFFIX%'")" = 0 ] \
    || { echo "ECHEC objets de test restants"; exit 1; }
}
trap cleanup EXIT

[ "$(run ledger_migrator comptabilite "CREATE TABLE ledger.$T (id serial PRIMARY KEY, n int); CREATE TABLE essai.$T (id serial PRIMARY KEY, n int);")" = ok ] \
  || { echo "ECHEC creation des tables de test par le migrateur"; exit 1; }

DB=comptabilite
expect "moteur insere dans ledger"             ok    ledger_engine   $DB "INSERT INTO ledger.$T (n) VALUES (1)"
expect "moteur modifie et supprime dans ledger" ok   ledger_engine   $DB "UPDATE ledger.$T SET n = 2; DELETE FROM ledger.$T"
expect "moteur insere dans essai"              ok    ledger_engine   $DB "INSERT INTO essai.$T (n) VALUES (1)"
expect "moteur NE PEUT PAS vider (TRUNCATE)"   42501 ledger_engine   $DB "TRUNCATE ledger.$T"
expect "moteur NE PEUT PAS creer de table"     42501 ledger_engine   $DB "CREATE TABLE ledger.ddl_$SUFFIX (n int)"
expect "personne ne cree dans public"          42501 ledger_engine   $DB "CREATE TABLE public.ddl_$SUFFIX (n int)"
expect "essai insere dans essai"               ok    ledger_essai    $DB "INSERT INTO essai.$T (n) VALUES (2)"
expect "essai NE PEUT PAS ecrire ledger"       42501 ledger_essai    $DB "INSERT INTO ledger.$T (n) VALUES (2)"
expect "essai NE PEUT PAS lire ledger"         42501 ledger_essai    $DB "SELECT * FROM ledger.$T"
expect "essai NE PEUT PAS avancer une sequence de ledger" 42501 ledger_essai $DB "SELECT nextval('ledger.${T}_id_seq')"
expect "Dorasso lit ledger"                    ok    ledger_dorasso  $DB "SELECT * FROM ledger.$T"
expect "Dorasso lit essai"                     ok    ledger_dorasso  $DB "SELECT * FROM essai.$T"
expect "Dorasso NE PEUT PAS ecrire ledger"     42501 ledger_dorasso  $DB "INSERT INTO ledger.$T (n) VALUES (3)"
expect "Dorasso NE PEUT PAS modifier essai"    42501 ledger_dorasso  $DB "UPDATE essai.$T SET n = 3"
expect "Dorasso NE PEUT PAS avancer une sequence" 42501 ledger_dorasso $DB "SELECT nextval('essai.${T}_id_seq')"
expect "Dorasso NE PEUT PAS prendre le role moteur" 42501 ledger_dorasso $DB "SET ROLE ledger_engine"
expect "aucun role applicatif sur la base postgres" 42501 ledger_engine postgres "SELECT 1"
expect "aucun role applicatif sur template1"   42501 ledger_dorasso  template1 "SELECT 1"
# A wrong password must be rejected (SQLSTATE 28P01), including on loopback
# (the image trusts 127.0.0.1 unless initialised with --auth-host=scram-sha-256).
if out=$(PGPASSWORD="mauvais-$SUFFIX" docker exec -i -e PGPASSWORD "$C" \
      psql -X -q -h 127.0.0.1 -U ledger_dorasso -d $DB -c "SELECT 1" 2>&1 >/dev/null); then
  got="connexion acceptee"
else
  got=$(sqlstate "$out")
fi
if [ "$got" = 28P01 ]; then echo "ok    mauvais mot de passe refuse"; else echo "ECHEC mauvais mot de passe (obtenu $got)"; fail=1; fi
# Current pg_hba file as parsed by PostgreSQL (not necessarily the rules loaded;
# effective authentication is the wrong-password test above, on loopback).
hba=$(admin "SELECT count(*) FROM pg_hba_file_rules WHERE (type <> 'local' AND auth_method <> 'scram-sha-256') OR error IS NOT NULL")
if [ "$hba" = 0 ]; then echo "ok    fichier pg_hba courant : aucune regle TCP sans mot de passe"; else echo "ECHEC pg_hba ($hba regle(s) sans mot de passe)"; fail=1; fi

exit $fail
