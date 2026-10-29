#!/bin/sh
# Somente bundles públicos com hash. HTML e service worker continuam na imagem.
# Sem volume configurado (dev/E2E), o nginx serve apenas a imagem normalmente.
set -eu
[ -n "${AULAS_ASSET_ARCHIVE:-}" ] || exit 0
asset_source="${AULAS_ASSET_SOURCE:-/usr/share/nginx/html/assets}"
asset_target="${AULAS_ASSET_ARCHIVE}/assets"
mkdir -p "$asset_target"

# Conta a janela desde a retirada da versão, mesmo se ela ficou meses ativa.
if [ -f "$AULAS_ASSET_ARCHIVE/.current-assets" ]; then
    while IFS= read -r asset_name; do
        case "$asset_name" in ''|.*|*/*) exit 1 ;; esac
        touch -c "$asset_target/$asset_name"
    done < "$AULAS_ASSET_ARCHIVE/.current-assets"
fi
: > "$AULAS_ASSET_ARCHIVE/.current-assets.tmp"

# Publicação atômica: uma interrupção não deixa um JS parcial sob nome imutável.
# Não preserva mtime do build: a retenção começa na última publicação da versão.
for asset_file in "$asset_source"/*; do
    [ -f "$asset_file" ] || continue
    asset_name="${asset_file##*/}"
    cp "$asset_file" "$asset_target/.${asset_name}.tmp"
    chmod 644 "$asset_target/.${asset_name}.tmp"
    mv -f "$asset_target/.${asset_name}.tmp" "$asset_target/$asset_name"
    printf '%s\n' "$asset_name" >> "$AULAS_ASSET_ARCHIVE/.current-assets.tmp"
done
mv -f "$AULAS_ASSET_ARCHIVE/.current-assets.tmp" "$AULAS_ASSET_ARCHIVE/.current-assets"

# Mais que os 30 dias do cache estático do PWA; só remove arquivos do arquivo
# público. Rascunhos, banco e gravações não são montados neste container.
find "$asset_target" -type f -mtime +30 -exec rm -f {} \;
