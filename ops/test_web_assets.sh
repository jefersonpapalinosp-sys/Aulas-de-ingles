#!/usr/bin/env bash
# Duas releases sintéticas no nginx real; sem API, banco ou volumes de estudo.
set -euo pipefail
asset_test_image="${1:-aulas-ingles-e2e-web:local}"
asset_test_dir="$(mktemp -d)"
asset_test_name="aulas-assets-test-$(date +%s)-$$"
asset_test_volume="${asset_test_name}-assets"
cleanup() {
  docker rm -f "$asset_test_name" >/dev/null 2>&1 || true
  docker volume rm "$asset_test_volume" >/dev/null 2>&1 || true
  rm -rf "$asset_test_dir"
}
trap cleanup EXIT
mkdir -p "$asset_test_dir/a/assets" "$asset_test_dir/b/assets"
printf 'shell A' > "$asset_test_dir/a/index.html"
printf 'worker A' > "$asset_test_dir/a/sw.js"
printf 'export const release = "A";' > "$asset_test_dir/a/assets/lazy-aaaaaaaa.js"
printf 'shell B' > "$asset_test_dir/b/index.html"
printf 'worker B' > "$asset_test_dir/b/sw.js"
printf 'export const release = "B";' > "$asset_test_dir/b/assets/lazy-bbbbbbbb.js"
chmod -R a+rX "$asset_test_dir"
docker volume create "$asset_test_volume" >/dev/null

start_release() {
  docker run -d --pull never --name "$asset_test_name" --read-only \
    --tmpfs /var/cache/nginx --tmpfs /var/run \
    -e AULAS_ASSET_ARCHIVE=/var/lib/aulas-web \
    -v "$asset_test_volume:/var/lib/aulas-web" \
    -v "$asset_test_dir/$1:/usr/share/nginx/html:ro" \
    -p 127.0.0.1::80 "$asset_test_image" >/dev/null
  asset_test_port="$(docker port "$asset_test_name" 80/tcp)"
  asset_test_url="http://${asset_test_port}"
  for _ in {1..30}; do
    if curl -fsS "$asset_test_url/" -o /dev/null 2>/dev/null; then return; fi
    sleep 1
  done
  docker logs "$asset_test_name"
  return 1
}

start_release a
# O chunk lazy A NÃO é solicitado antes da troca, como no incidente do Caderno.
test "$(curl -fsS "$asset_test_url/")" = 'shell A'
docker rm -f "$asset_test_name" >/dev/null
start_release b
curl -fsS "$asset_test_url/assets/lazy-aaaaaaaa.js" -D "$asset_test_dir/headers" -o "$asset_test_dir/body"
cmp "$asset_test_dir/body" "$asset_test_dir/a/assets/lazy-aaaaaaaa.js"
grep -qi 'Content-Type: application/javascript' "$asset_test_dir/headers"
grep -qi 'Cache-Control: public, max-age=31536000, immutable' "$asset_test_dir/headers"
test "$(curl -fsS "$asset_test_url/assets/lazy-bbbbbbbb.js")" = 'export const release = "B";'
test "$(curl -fsS "$asset_test_url/")" = 'shell B'
test "$(curl -fsS "$asset_test_url/caderno?course=voa-level-1&unit=1-5")" = 'shell B'
test "$(curl -fsS "$asset_test_url/sw.js")" = 'worker B'
test "$(curl -sS -D "$asset_test_dir/missing-headers" -o /dev/null -w '%{http_code}' "$asset_test_url/assets/absent.js")" = 404
if grep -qi 'immutable' "$asset_test_dir/missing-headers"; then
  echo 'Erro: resposta 404 recebeu cache imutável.' >&2
  exit 1
fi
echo 'Retenção validada: chunk lazy antigo íntegro, shell/SW atuais e asset ausente 404 sem cache imutável.'
