#!/usr/bin/env bash
# Atualiza o sistema publicado: baixa a versão nova, faz backup do banco e sobe.
# As migrations entram sozinhas quando a API inicia. Uso (no servidor): ./deploy/atualizar.sh
set -euo pipefail
cd "$(dirname "$0")/.."
C="docker compose -f docker-compose.web.yml"

mkdir -p backups
if $C ps db --status running -q | grep -q .; then
  arq="backups/inpi_$(date +%Y%m%d_%H%M%S).sql.gz"
  $C exec -T db pg_dump -U postgres inpi | gzip > "$arq"
  echo "Backup salvo em $arq"
  ls -1t backups/*.sql.gz | tail -n +15 | xargs -r rm --   # mantém os 14 mais recentes
fi

git pull --ff-only
$C up -d --build
sleep 8
$C ps
curl -fsS "http://localhost:80/health" -H "Host: ${DOMINIO:-localhost}" >/dev/null 2>&1 || true
echo "Atualizado. Confira https://$(grep -E '^DOMINIO=' .env | cut -d= -f2)/health"
