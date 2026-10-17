#!/usr/bin/env bash
# Prove the least-privilege rules of Dorasso's accounting database on the running
# container: creates throw-away tables as the migrator, then checks what each role
# can and cannot do. Exit code 0 only if every expectation holds. Business data is
# never touched: the probe tables are created for the test and dropped afterwards.
set -uo pipefail
C=${LEDGER_CONTAINER:-dorasso-ledger-1}
DIR="${LOCALAPPDATA:-$HOME/.local/share}/Dorasso/ledger"
fail=0

sql() { # role, statement -> exit status of psql (password from the private file)
  docker exec -i -e PGPASSWORD="$(cat "$DIR/$1.password")" "$C" \
    psql -q -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -U "$1" -d comptabilite -c "$2" >/dev/null 2>&1
}
expect() { # description, expected (ok|deny), role, statement
  if sql "$3" "$4"; then got=ok; else got=deny; fi
  if [ "$got" = "$2" ]; then echo "ok    $1"; else echo "ECHEC $1 (attendu $2, obtenu $got)"; fail=1; fi
}

sql ledger_migrator "CREATE TABLE IF NOT EXISTS ledger.probe_isolation (n int); CREATE TABLE IF NOT EXISTS essai.probe_isolation (n int);" \
  || { echo "ECHEC creation des tables de test par le migrateur"; exit 1; }

expect "moteur ecrit dans ledger"          ok   ledger_engine  "INSERT INTO ledger.probe_isolation VALUES (1)"
expect "moteur ecrit dans essai"           ok   ledger_engine  "INSERT INTO essai.probe_isolation VALUES (1)"
expect "essai ecrit dans essai"            ok   ledger_essai   "INSERT INTO essai.probe_isolation VALUES (2)"
expect "essai NE PEUT PAS ecrire ledger"   deny ledger_essai   "INSERT INTO ledger.probe_isolation VALUES (2)"
expect "essai NE PEUT PAS lire ledger"     deny ledger_essai   "SELECT * FROM ledger.probe_isolation"
expect "Dorasso lit ledger"                ok   ledger_dorasso "SELECT * FROM ledger.probe_isolation"
expect "Dorasso lit essai"                 ok   ledger_dorasso "SELECT * FROM essai.probe_isolation"
expect "Dorasso NE PEUT PAS ecrire ledger" deny ledger_dorasso "INSERT INTO ledger.probe_isolation VALUES (3)"
expect "Dorasso NE PEUT PAS ecrire essai"  deny ledger_dorasso "INSERT INTO essai.probe_isolation VALUES (3)"
expect "moteur NE PEUT PAS creer de table" deny ledger_engine  "CREATE TABLE ledger.probe_ddl (n int)"
expect "personne ne cree dans public"      deny ledger_engine  "CREATE TABLE public.probe_ddl (n int)"

sql ledger_migrator "DROP TABLE ledger.probe_isolation; DROP TABLE essai.probe_isolation;"
exit $fail
