#!/bin/sh
set -eu

# O Docker cria a raiz de volumes nomeados como root. Ajustamos somente o
# diretório conhecido das gravações e iniciamos o processo da API sem root.
mkdir -p /app/data/speaking
chown app:app /app/data/speaking
chmod 700 /app/data/speaking

exec gosu app "$@"
