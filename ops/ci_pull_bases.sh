#!/usr/bin/env bash
# Pré-carrega no cache do runner as imagens-base dos Dockerfiles, por digest e
# com duas origens equivalentes. `docker build` resolve um FROM já presente no
# cache local sem consultar o registro (conferido em 2026-10-21), então o build
# deixa de depender do limite anônimo de pull do espelho da AWS ou do Docker Hub.
# Não inicia containers nem volumes.
set -euo pipefail

# alias usado nos FROM | repositório | digest do índice OCI, idêntico nas duas
# origens (reconferido em 2026-10-26 com `docker buildx imagetools inspect`).
# Ao mudar um FROM, atualizar a linha correspondente e reconferir o digest.
#
# O digest do nginx mudou sem o tag mudar: o upstream republicou
# `1.30.6-alpine3.24` sobre o alpine 3.24.3, que corrige CVE-2026-77214
# (libexpat) e CVE-2026-88806 (libx11). Re-ancorar aqui é o que faz o CI
# construir com os pacotes corrigidos — o tag sozinho não garante isso.
ci_base_images=(
  "public.ecr.aws/docker/library/python:3.12.15-alpine3.24|library/python|sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4"
  "public.ecr.aws/docker/library/node:24.22.0-alpine3.24|library/node|sha256:44fce696f38ba8c987c4db89954051000bbd05ffd8d8659ba15ed4a8602e937f"
  "public.ecr.aws/docker/library/nginx:1.30.6-alpine3.24|library/nginx|sha256:47928bf67eb62a1863cb08d9ecb52d3e704304ba614eaee17884204677702951"
  # ops/rollback_image.py constrói o commit fixo d0b1f8c, cuja base ainda é 3.12-slim.
  "public.ecr.aws/docker/library/python:3.12-slim|library/python|sha256:2259debdc6af85626058a15a7bf44ad6a68b8c98c9ae82a02cf5cdb92f096d47"
)

ci_base_pull() {
  local ci_base_alias="$1" ci_base_repo="$2" ci_base_digest="$3"
  local ci_base_attempt ci_base_registry ci_base_source ci_base_wait
  for ci_base_attempt in 1 2 3 4; do
    for ci_base_registry in "public.ecr.aws/docker/${ci_base_repo}" "docker.io/${ci_base_repo}"; do
      ci_base_source="${ci_base_registry}@${ci_base_digest}"
      if docker pull --quiet "$ci_base_source"; then
        # O Docker valida o digest no pull; o alias é exatamente o FROM dos Dockerfiles.
        docker tag "$ci_base_source" "$ci_base_alias"
        echo "Imagem-base verificada por digest: ${ci_base_alias} via ${ci_base_registry}."
        return 0
      fi
      echo "::warning::download de ${ci_base_alias} via ${ci_base_registry} indisponível na tentativa ${ci_base_attempt}"
    done
    if [ "$ci_base_attempt" -lt 4 ]; then
      ci_base_wait=$((ci_base_attempt * 45))
      sleep "$ci_base_wait"
    fi
  done
  echo "::error::nenhuma origem entregou ${ci_base_alias} após 4 tentativas"
  return 1
}

for ci_base_entry in "${ci_base_images[@]}"; do
  IFS='|' read -r ci_base_alias ci_base_repo ci_base_digest <<<"$ci_base_entry"
  ci_base_pull "$ci_base_alias" "$ci_base_repo" "$ci_base_digest"
done
