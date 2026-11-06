#!/usr/bin/env bash
# Cliente compatível com make/CI. O servidor é instalado fora da árvore publicada.
# Uso: ops/deploy_public.sh [--dry-run] [--skip-smoke] <sha> | --rollback
set -euo pipefail
exec python3 -m ops.deploy_client "$@"
