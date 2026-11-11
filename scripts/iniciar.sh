#!/usr/bin/env bash
# Sobe o sistema inteiro: banco (Docker), API, worker dos agentes e telas.
# Na primeira vez também instala as dependências (~3 min). Uso: bash scripts/iniciar.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs

passo() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }

passo "1/5 Banco de dados"
if pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
  echo "Postgres já está rodando em localhost:5432"
else
  docker compose up -d db
  printf "Aguardando o Postgres"
  until docker compose exec -T db pg_isready -U postgres >/dev/null 2>&1; do printf "."; sleep 1; done
  echo " ok"
fi

passo "2/5 Backend (Python)"
[ -x backend/.venv/bin/python ] || python3 -m venv backend/.venv
if [ ! -f backend/.venv/.instalado ] || [ backend/pyproject.toml -nt backend/.venv/.instalado ]; then
  backend/.venv/bin/pip install -q --upgrade pip
  backend/.venv/bin/pip install -q -e "./backend[dev]"
  touch backend/.venv/.instalado
fi
[ -f backend/.env ] || cp backend/.env.example backend/.env
(cd backend && .venv/bin/python -m app.migrate)

passo "3/5 Frontend (Node)"
[ -f frontend/.env.local ] || cp frontend/.env.example frontend/.env.local
if [ ! -d frontend/node_modules ] || [ frontend/package-lock.json -nt frontend/node_modules/.package-lock.json ]; then
  (cd frontend && npm ci --no-audit --no-fund)
fi

passo "4/5 Iniciando API, worker e telas"
trap 'echo; echo "Encerrando..."; kill $(jobs -p) 2>/dev/null || true' EXIT INT TERM
(cd backend && exec .venv/bin/uvicorn app.main:app --port 8000) > logs/api.log 2>&1 &
(cd backend && exec .venv/bin/python -m app.worker) > logs/worker.log 2>&1 &
(cd frontend && exec npm run dev -- -p 3000) > logs/web.log 2>&1 &

printf "Aguardando as telas"
for _ in $(seq 1 120); do
  if curl -fsS http://localhost:3000/health >/dev/null 2>&1; then break; fi
  printf "."; sleep 1
done
echo
curl -fsS http://localhost:3000/health >/dev/null || { echo "As telas não subiram. Veja logs/web.log e logs/api.log"; exit 1; }

passo "5/5 Pronto!"
if [ -n "${CODESPACE_NAME:-}" ]; then
  echo "Abra: https://${CODESPACE_NAME}-3000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  echo "(ou na aba PORTAS, clique no globo da porta 3000)"
else
  echo "Abra: http://localhost:3000"
fi
cat <<'MSG'

Para importar a RPI: tela "Edições da RPI" > "Verificar novas edições".
Abaixo aparece o que os agentes estão fazendo. Para parar tudo: Ctrl+C.
Logs completos na pasta logs/.

MSG
tail -n 0 -f logs/worker.log
