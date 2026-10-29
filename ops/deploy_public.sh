#!/usr/bin/env bash
# Deploy da stack pública do EasyPanel (projeto papalino, serviço aulas-ingles)
# por SSH, reproduzindo o procedimento registrado em docs/deploy_easypanel.md
# ("Registro do segundo deploy — 21/10/2026"): o diretório code/ do serviço não
# é um repositório Git, então o SHA aprovado sai de `git archive`, entra por
# rsync preservando o que o painel gera (.env e docker-compose.override.yml) e a
# stack sobe com o mesmo comando que o painel executa. O gate é o do Compose
# (migrate → permissions → api → web); aqui ele é conferido de novo pelos
# códigos de saída dos one-shots e por smokes HTTPS na origem pública.
#
# Uso: ops/deploy_public.sh [--dry-run] [--skip-smoke] <sha>
#   <sha>                  commit já integrado em origin/main (abreviado ou completo)
#   --dry-run              imprime cada comando sem contatar a VM
#   --skip-smoke           não executa os smokes HTTPS ao final
#   AULAS_PUBLIC_SSH_HOST  destino SSH (padrão root@72.61.39.94, o mesmo do backup)
#   AULAS_PUBLIC_URL       origem HTTPS dos smokes (padrão: domínio gerado pelo painel)
#   AULAS_DEPLOY_ORIGIN    texto livre gravado em code/.deployed-sha (padrão: automático)
#
# O script nunca lê nem imprime o .env remoto. SSH sempre em BatchMode com
# StrictHostKeyChecking=yes: a chave da VM precisa já estar em known_hosts; um
# host desconhecido é recusado, não aceito.
set -euo pipefail

deploy_host="${AULAS_PUBLIC_SSH_HOST:-root@72.61.39.94}"
deploy_url="${AULAS_PUBLIC_URL:-https://papalino-aulas-ingles.aeuv6j.easypanel.host}"
deploy_service_dir="/etc/easypanel/projects/papalino/aulas-ingles"
deploy_code_dir="${deploy_service_dir}/code"
deploy_compose_dir="${deploy_code_dir}/infra/easypanel"
deploy_project="papalino_aulas-ingles"
deploy_compose="docker compose -p ${deploy_project} --env-file .env -f compose.yml -f docker-compose.override.yml"
deploy_wait_timeout=420
deploy_smoke_paths="/ /sw.js /api/live /api/health /api/courses"
deploy_ssh_options=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes)
deploy_dry_run=0
deploy_skip_smoke=0
deploy_sha=""
deploy_prefix="+"

usage() {
  echo "uso: ops/deploy_public.sh [--dry-run] [--skip-smoke] <sha de origin/main>"
}

die() {
  echo "::error::$*"
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) deploy_dry_run=1; deploy_prefix="[dry-run]" ;;
    --skip-smoke) deploy_skip_smoke=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) usage; die "opção desconhecida: $1" ;;
    "") ;; # `make deploy-public` sem sha= chega aqui como argumento vazio
    *)
      [ -z "$deploy_sha" ] || { usage; die "informe um único SHA"; }
      deploy_sha="$1"
      ;;
  esac
  shift
done
[ -n "$deploy_sha" ] || { usage; die "informe o SHA aprovado (make deploy-public sha=<sha>)"; }

# (a) Só um commit já integrado em origin/main vai à produção: branch, tag ou
# commit de trabalho são recusados antes de qualquer contato com a VM.
case "$deploy_sha" in
  *[!0-9a-fA-F]*) die "SHA inválido: ${deploy_sha} (use o hash do commit, não branch ou tag)" ;;
esac
[ "${#deploy_sha}" -ge 7 ] && [ "${#deploy_sha}" -le 40 ] \
  || die "SHA inválido: ${deploy_sha} (7 a 40 dígitos hexadecimais)"
deploy_full_sha="$(git rev-parse --verify --quiet "${deploy_sha}^{commit}")" \
  || die "commit ${deploy_sha} não existe neste clone; faça git fetch origin main"
git merge-base --is-ancestor "$deploy_full_sha" origin/main \
  || die "commit ${deploy_full_sha} não está integrado em origin/main; só SHAs da main vão à produção"

deploy_tmp="$(mktemp -d "${TMPDIR:-/tmp}/aulas-deploy.XXXXXX")"
trap 'rm -rf "$deploy_tmp"' EXIT

deploy_stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [ -n "${AULAS_DEPLOY_ORIGIN:-}" ]; then
  deploy_origin="$AULAS_DEPLOY_ORIGIN"
elif [ "${GITHUB_ACTIONS:-}" = true ]; then
  deploy_origin="github-actions ${GITHUB_REPOSITORY:-?} run ${GITHUB_RUN_ID:-?}"
else
  deploy_origin="manual via ssh por $(id -un)"
fi
case "$deploy_origin" in
  *[\'\"\\\$\`]*) die "AULAS_DEPLOY_ORIGIN não pode conter aspas, barra invertida, \$ ou crase" ;;
esac

show() {
  printf '%s %s\n' "$deploy_prefix" "$*"
}

# Executa um comando na VM com stdin fechado; em dry-run só o imprime.
remote() {
  show "ssh ${deploy_host} -- $1"
  [ "$deploy_dry_run" = 0 ] || return 0
  # shellcheck disable=SC2029  # a expansão é local de propósito: o comando
  # remoto é montado aqui, com SHA e caminhos já resolvidos.
  ssh "${deploy_ssh_options[@]}" "$deploy_host" "$1" < /dev/null
}

# Igual a remote, guardando a saída remota em $2 para o script ler.
remote_capture() {
  show "ssh ${deploy_host} -- $1"
  [ "$deploy_dry_run" = 0 ] || return 0
  # shellcheck disable=SC2029  # idem: comando montado localmente.
  ssh "${deploy_ssh_options[@]}" "$deploy_host" "$1" < /dev/null > "$2"
}

echo "Deploy público: ${deploy_full_sha} → ${deploy_host}:${deploy_code_dir}"

# Pré-voo: nada é alterado se faltar o que o painel gera ou alguma ferramenta.
deploy_preflight="test -d ${deploy_code_dir} && test -f ${deploy_compose_dir}/compose.yml && test -f ${deploy_compose_dir}/.env && test -f ${deploy_compose_dir}/docker-compose.override.yml && command -v rsync >/dev/null && docker compose version >/dev/null"
remote "$deploy_preflight" \
  || die "pré-voo falhou: diretório do serviço, .env/override gerados pelo painel, rsync ou docker compose ausentes na VM"

# (b) O conteúdo do commit vai por git archive, sem depender de Git na VM.
deploy_stage="/tmp/aulas-deploy-${deploy_full_sha}"
deploy_extract="rm -rf ${deploy_stage} && mkdir -p ${deploy_stage} && tar -x -C ${deploy_stage}"
show "git archive --format=tar ${deploy_full_sha} | ssh ${deploy_host} -- ${deploy_extract}"
if [ "$deploy_dry_run" = 0 ]; then
  # shellcheck disable=SC2029  # $deploy_extract traz o stage já resolvido.
  git archive --format=tar "$deploy_full_sha" \
    | ssh "${deploy_ssh_options[@]}" "$deploy_host" "$deploy_extract"
fi

# (c) rsync --delete deixa code/ idêntico ao commit, exceto o que o painel gera.
# Com --exclude os caminhos ficam protegidos também da remoção. O marcador segue
# o formato já existente na VM: "<sha> <data UTC> <origem>".
deploy_sync="rsync -a --delete --exclude=/docker-compose.override.yml --exclude=/infra/easypanel/.env --exclude=/infra/easypanel/docker-compose.override.yml ${deploy_stage}/ ${deploy_code_dir}/ && printf '%s %s %s\n' ${deploy_full_sha} ${deploy_stamp} '${deploy_origin}' > ${deploy_code_dir}/.deployed-sha && rm -rf ${deploy_stage}"
remote "$deploy_sync" || {
  remote "rm -rf ${deploy_stage}" || true
  die "rsync falhou; code/ pode ter ficado parcial — refaça o deploy deste SHA ou do anterior"
}

# (d) O mesmo comando que o painel executa; --wait segura até api/web saudáveis
# e os one-shots concluídos. A falha não encerra aqui: antes mostramos o estado.
deploy_up="cd ${deploy_compose_dir} && ${deploy_compose} up -d --build --remove-orphans --wait --wait-timeout ${deploy_wait_timeout}"
deploy_up_status=0
remote "$deploy_up" || deploy_up_status=$?

# (e) Estado da stack e códigos de saída dos one-shots do gate.
remote "cd ${deploy_compose_dir} && ${deploy_compose} ps -a" || true
deploy_oneshots="cd ${deploy_compose_dir} && for s in migrate permissions seed; do c=\$(${deploy_compose} ps -aq \"\$s\" 2>/dev/null | head -n 1); if [ -z \"\$c\" ]; then echo \"\$s absent\"; else echo \"\$s \$(docker inspect -f '{{.State.ExitCode}}' \"\$c\")\"; fi; done"
remote_capture "$deploy_oneshots" "${deploy_tmp}/oneshots" \
  || die "não foi possível ler os códigos de saída de migrate/permissions"

deploy_gate_failed=0
if [ "$deploy_dry_run" = 0 ]; then
  deploy_seen=""
  while read -r deploy_svc deploy_code; do
    case "$deploy_svc" in
      migrate|permissions|seed) ;;
      *) continue ;;
    esac
    deploy_seen="${deploy_seen} ${deploy_svc}"
    if [ "$deploy_code" = absent ]; then
      if [ "$deploy_svc" = seed ]; then
        echo "seed: sem serviço próprio nesta stack (roda dentro de migrate); nada a conferir."
      else
        echo "::error::${deploy_svc}: nenhum container encontrado após o up"
        deploy_gate_failed=1
      fi
    elif [ "$deploy_code" = 0 ]; then
      echo "${deploy_svc}: saída 0"
    else
      echo "::error::${deploy_svc}: saída ${deploy_code}"
      deploy_gate_failed=1
    fi
  done < "${deploy_tmp}/oneshots"
  for deploy_svc in migrate permissions; do
    case " ${deploy_seen} " in
      *" ${deploy_svc} "*) ;;
      *) echo "::error::${deploy_svc}: código de saída não reportado"; deploy_gate_failed=1 ;;
    esac
  done
fi
if [ "$deploy_up_status" != 0 ] || [ "$deploy_gate_failed" != 0 ]; then
  remote "cd ${deploy_compose_dir} && ${deploy_compose} logs --no-color --tail=80 migrate permissions" || true
  die "gate de release reprovado (compose up saiu com ${deploy_up_status}); a stack ficou como o Compose a deixou — leia o primeiro erro, corrija e refaça o deploy"
fi

# (f) Smokes HTTPS na origem pública: 200 nas cinco rotas e schema compatível.
deploy_smoke() {
  local deploy_path="$1" deploy_body="$2" deploy_attempt deploy_status
  for deploy_attempt in 1 2 3; do
    show "curl -sS -o <corpo> -w '%{http_code}' --max-time 30 ${deploy_url}${deploy_path}"
    [ "$deploy_dry_run" = 0 ] || return 0
    deploy_status="$(curl -sS -o "$deploy_body" -w '%{http_code}' --max-time 30 "${deploy_url}${deploy_path}" || true)"
    if [ "$deploy_status" = 200 ]; then
      echo "smoke ${deploy_path}: 200"
      return 0
    fi
    echo "smoke ${deploy_path}: HTTP ${deploy_status:-000} na tentativa ${deploy_attempt}"
    if [ "$deploy_attempt" -lt 3 ]; then
      sleep 5
    fi
  done
  echo "::error::smoke ${deploy_path} não respondeu 200 em 3 tentativas"
  return 1
}

if [ "$deploy_skip_smoke" = 1 ]; then
  echo "smokes HTTPS pulados (--skip-smoke)."
else
  deploy_smoke_failed=0
  for deploy_path in $deploy_smoke_paths; do
    deploy_body="${deploy_tmp}/body$(echo "$deploy_path" | tr '/.' '__')"
    deploy_smoke "$deploy_path" "$deploy_body" || deploy_smoke_failed=1
  done
  [ "$deploy_smoke_failed" = 0 ] || die "smoke HTTPS reprovado em ${deploy_url}"
  if [ "$deploy_dry_run" = 0 ]; then
    python3 - "${deploy_tmp}/body_api_health" <<'PY' || die "/api/health sem schema compatível"
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    health = json.load(handle)
print(
    "health:",
    "status=%s" % health.get("status"),
    "db=%s" % health.get("db"),
    "schema=%s" % health.get("schema"),
)
if health.get("status") != "ok" or health.get("db") != "up" or health.get("schema") != "compatible":
    print("::error::readiness pública incompatível em /api/health")
    sys.exit(1)
PY
  else
    show "python3: confere status=ok, db=up e schema=compatible no JSON público de /api/health"
  fi
fi

if [ "$deploy_dry_run" = 1 ]; then
  echo "Dry-run concluído: nenhum comando remoto foi executado."
else
  echo "Deploy público concluído: ${deploy_full_sha} em ${deploy_url} (${deploy_stamp})."
fi
