#!/bin/sh
set -eu
set -f

# Só endereços revisados pelo operador; nunca confiar em todas as redes privadas.
# /var/run é tmpfs também nos perfis com filesystem somente leitura.
proxy_ranges=${AULAS_TRUSTED_PROXY_CIDRS:-}
if [ "${AULAS_REQUIRE_TRUSTED_PROXY:-false}" = true ] && [ -z "$proxy_ranges" ]; then
    echo 'Configure AULAS_TRUSTED_PROXY_CIDRS para o proxy de entrada.' >&2
    exit 1
fi
proxy_temp=$(mktemp /var/run/aulas-proxy.XXXXXX)
trap 'rm -f "$proxy_temp"' EXIT HUP INT TERM
printf 'geo $realip_remote_addr $aulas_trusted_proxy {\n    default 0;\n' > "$proxy_temp"
proxy_directives=''
proxy_count=0
for proxy_range in $(printf '%s' "$proxy_ranges" | tr ',' ' '); do
    case "$proxy_range" in
        *:*) case "$proxy_range" in *[!0-9a-fA-F:./]*) exit 1 ;; esac ;;
        *.*) case "$proxy_range" in *[!0-9./]*) exit 1 ;; esac ;;
        *) echo 'Proxy confiável deve ser IP ou CIDR, sem hostname.' >&2; exit 1 ;;
    esac
    case "$proxy_range" in
        */*)
            proxy_prefix=${proxy_range##*/}
            case "$proxy_prefix" in ''|*[!0-9]*) exit 1 ;; esac
            if [ "$proxy_prefix" -eq 0 ]; then
                echo 'Não é permitido confiar em toda a internet.' >&2
                exit 1
            fi
            ;;
    esac
    printf '    %s 1;\n' "$proxy_range" >> "$proxy_temp"
    proxy_directives="$proxy_directives
set_real_ip_from $proxy_range;"
    proxy_count=$((proxy_count + 1))
done
if [ "${AULAS_REQUIRE_TRUSTED_PROXY:-false}" = true ] && [ "$proxy_count" -eq 0 ]; then
    echo 'A lista de proxies confiáveis está vazia.' >&2
    exit 1
fi
printf '}\n%s\n' "$proxy_directives" >> "$proxy_temp"
mv "$proxy_temp" /var/run/aulas-trusted-proxies.conf
