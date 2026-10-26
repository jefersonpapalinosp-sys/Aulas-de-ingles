#!/bin/sh
set -eu

# O Docker cria a raiz de volumes nomeados como root. Ajustamos somente o
# diretório conhecido das gravações e iniciamos o processo sem root.
#
# Três situações legítimas tornam esse ajuste impossível, e nenhuma delas é
# erro: o volume montado `read_only` (worker, que só lê o áudio), o sistema de
# arquivos do container em `read_only: true`, e a execução já sem root. Em
# todas, não há nada a ajustar — quem não pode gravar no diretório também não
# vai precisar dele gravável. Tolerar a falha aqui é o que permite ao worker
# usar este mesmo entrypoint, em vez de `entrypoint: []` com o UID da imagem
# repetido no Compose.
if mkdir -p /app/data/speaking 2>/dev/null; then
    chown app:app /app/data/speaking 2>/dev/null || true
    chmod 700 /app/data/speaking 2>/dev/null || true
fi

# `su-exec` é no-op quando o container já roda como `app`: setuid para o mesmo
# UID não exige privilégio. Começando como root, exige CAP_SETUID/CAP_SETGID —
# é por isso que os serviços com `cap_drop: [ALL]` readicionam só esses dois.
exec su-exec app "$@"
