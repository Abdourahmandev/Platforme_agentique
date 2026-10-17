#!/bin/sh
# Durable lock for Dorasso's accounting database. An initialised volume without the
# marker written by the last step of init-roles.sh means the security initialisation
# did not complete (the official entrypoint skips init scripts on later starts):
# PostgreSQL is then never started on that volume. Recovery: recreate the volume.
set -eu
if [ -s "$PGDATA/PG_VERSION" ] && [ ! -f "$PGDATA/dorasso-securite-ok" ]; then
  echo "Refus : initialisation de securite incomplete pour ce volume; a recreer." >&2
  exit 1
fi
exec docker-entrypoint.sh "$@"
