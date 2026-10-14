#!/usr/bin/env bash
# Prepara apenas o cache de imagens do runner; não inicia containers/volumes.
set -euo pipefail

ci_postgres_image="public.ecr.aws/docker/library/postgres:16.15-alpine"
# Índice OCI idêntico nos dois registros, conferido em 2026-10-14.
# Ao atualizar o PostgreSQL, atualizar o tag e verificar este digest novamente.
ci_postgres_digest="sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"

for ci_postgres_attempt in 1 2 3 4; do
  for ci_postgres_registry in public.ecr.aws/docker/library/postgres docker.io/library/postgres; do
    ci_postgres_source="${ci_postgres_registry}@${ci_postgres_digest}"
    if docker pull --quiet "$ci_postgres_source"; then
      # O Docker valida o digest no pull; ambas as origens entregam o mesmo conteúdo.
      # O alias atende os Compose existentes, sem modificar ambientes de estudo.
      docker tag "$ci_postgres_source" "$ci_postgres_image"
      echo "PostgreSQL verificado por digest, via ${ci_postgres_registry}."
      exit 0
    fi
    echo "::warning::download via ${ci_postgres_registry} indisponível na tentativa ${ci_postgres_attempt}"
  done
  if [ "$ci_postgres_attempt" -lt 4 ]; then
    ci_postgres_wait=$((ci_postgres_attempt * 45))
    sleep "$ci_postgres_wait"
  fi
done
echo "::error::nenhuma origem entregou o PostgreSQL esperado após 4 tentativas"
exit 1
