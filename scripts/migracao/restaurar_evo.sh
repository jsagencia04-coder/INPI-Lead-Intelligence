#!/bin/sh
# Restaura no destino a Evolution do INPI (banco + sessão) enviada por evo_enviar.js. Roda no container evo-restaurar.
# Não imprime segredos.
set -eu
export PGPASSWORD="$EVO_DB_PASSWORD"
H="-h evolution-db -U postgres -d evo"
# Proteção: roda uma única vez (o painel pode subir o serviço de novo; não pode sobrescrever a Evolution em uso).
if [ "$(psql $H -Atc "select to_regclass('public._migracao_restaurada') is not null")" = "t" ]; then
  echo "evolution ja restaurada; nada a fazer"; exit 0
fi
pg_restore $H --clean --if-exists --no-owner --no-privileges /migracao/evo.dump
psql $H -v ON_ERROR_STOP=1 -q -c "update \"Webhook\" set url = 'http://api:8000/webhooks/evolution/${EVOLUTION_INSTANCE_NAME:-inpi-agent}?token=${EVOLUTION_WEBHOOK_TOKEN}', enabled = true"
psql $H -At -c "select 'instancias=' || count(*) from \"Instance\"" -c "select 'webhooks=' || count(*) from \"Webhook\"" -c "select 'sessoes=' || count(*) from \"Session\""
find /evolution/instances -mindepth 1 -delete
tar xzf /migracao/evo_instances.tar.gz -C /evolution/instances
echo "arquivos_sessao=$(find /evolution/instances -type f | wc -l)"
psql $H -q -c "create table _migracao_restaurada (em timestamptz default now()); insert into _migracao_restaurada default values"
