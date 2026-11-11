# INPI Lead Intelligence

Plataforma que identifica, a partir da RPI semanal, titulares de marcas sem procurador
e os transforma em leads qualificados, com fonte e trilha de auditoria para cada dado.

**Status: v1.0, Fases 1 a 7 implementadas.** Veja `docs/ARQUITETURA.md` (decisões e regras) e
`docs/IMPLANTACAO.md` (colocar no ar).

| Fase | O que faz |
|---|---|
| 1 | Estrutura, fila de jobs, auditoria, autenticação |
| 2 | Agentes 01 e 02: coleta e interpretação da RPI (XML oficial) |
| 3 | Agente 03: consulta ao INPI (pePI). Confirma procurador, marca e situação |
| 4 | Base CNPJ da Receita + Agente 04: pesquisa web com Claude, sempre com evidência |
| 5 | Agentes 05 e 06: validação de contatos, deduplicação, homônimos, score, resumo, prospecção com aprovação, opt-out |
| 6 | Dashboard, tela do lead, revisões, relatórios semanais, exportação Excel/CSV |
| 7 | Teste ponta a ponta, Docker, Render/Vercel/Supabase, métricas e operação |

## Estrutura

```
supabase/migrations/   Schema do banco (SQL puro; vale para Postgres local e Supabase)
backend/               FastAPI (API) + worker dos agentes + fila de jobs no Postgres
  app/agents/          Agentes: rpi, inpi, cnpj, research, leads (13 tipos de job)
  app/inpi/            Cliente e parser do pePI
  app/cnpj/            Leitura econômica da base CNPJ da Receita
  app/llm.py           Claude API com controle de custo
  app/validation.py    Validação de contatos
  app/rpi/             Leitura do índice da RPI, parser do XML de marcas e importação
  app/jobs/            Fila (enqueue / claim SKIP LOCKED / retry com backoff)
  app/storage.py       Armazenamento imutável dos originais (local ou Supabase Storage)
  tests/               46 testes, incluindo o pipeline completo com INPI, Receita e Claude simulados
frontend/              Next.js + TypeScript + Tailwind + shadcn/ui
docs/                  Arquitetura e decisões
```

## Testar no navegador (GitHub Codespaces)

Veja `docs/TESTAR_NO_GITHUB.md`. Resumo: crie um repositório, abra um Codespace, envie o zip e rode `bash scripts/iniciar.sh`.

## Rodando localmente

Pré-requisitos: Python 3.11+, Node 22+, Docker (ou um Postgres 16 qualquer).

```bash
# 1. Banco
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
python -m app.migrate                                 # aplica supabase/migrations
uvicorn app.main:app --reload                         # API em http://localhost:8000/docs

# 3. Worker (outro terminal, mesmo venv)
python -m app.worker

# 4. Frontend (outro terminal)
cd frontend
cp .env.example .env.local
npm install
npm run dev                                           # http://localhost:3000
```

## Importando a RPI (Fase 2)

Com a API, o worker e o frontend rodando:

1. Abra **Edições da RPI** e clique em **Verificar novas edições**.
2. O worker lê o índice do INPI, baixa o `RM<N>.zip` da edição mais recente, guarda o
   original e interpreta o XML. Leva cerca de 1 minuto.
3. Veja o resultado em **Processos** (filtro "Elegíveis") e no **Dashboard**.

A partir daí, o worker verifica sozinho a cada 3 horas (tabela `schedules`). Para importar
edições anteriores, defina `RPI_START_EDITION` no `.env` (ex.: `2900`) antes de verificar.

Se o site do INPI estiver fora do ar, baixe o XML manualmente em
https://revistas.inpi.gov.br/rpi/ (coluna Marcas, link "XML") e use **Enviar RM.zip**.

**Conferência da primeira importação (RPI 2914, 10/11/2026).** Contagens medidas no XML
oficial durante o desenvolvimento:

| Indicador | Esperado |
|---|---|
| Processos no XML | 38.336 |
| Elegíveis: oposição (IPAS009) | 4.451 |
| Elegíveis: indeferimento (IPAS024) | 607 |
| Elegíveis: exigências (IPAS136/267/005/192) | ~187 |
| Elegíveis: extinção por fim da vigência (IPAS161) | 168 |

Pequenas diferenças (de poucas unidades) podem vir do critério de titular estrangeiro.
Diferenças grandes indicam problema: me avise.

## Depois da RPI: o que acontece sozinho

Com o worker rodando, os agendamentos (tela **Operação**) fazem o resto:

1. **A cada hora:** consulta ao INPI dos processos elegíveis (100 por hora, com pausa
   entre as consultas). Confirma a ausência de procurador e completa marca e situação.
2. **A cada hora:** montagem dos leads (1 por titular), com score e prioridade.
3. **A cada hora (grátis):** leitura dos sites oficiais dos titulares com ausência de procurador
   confirmada. Extrai e-mail, telefone, WhatsApp e redes, só quando o site cita o CNPJ, a
   razão social ou o nome fantasia.
4. **A cada hora, se houver `ANTHROPIC_API_KEY`:** pesquisa web dos leads de prioridade
   alta e média com ausência de procurador confirmada, dentro do orçamento semanal. Em
   seguida, a validação dos contatos encontrados.
5. **A cada 2 horas:** resumo e sugestão de abordagem. Sem chave de API, usa um texto fixo.
6. **Diariamente:** o relatório da última edição.
7. **Desligado por padrão:** cruzamento com a base CNPJ da Receita (baixa cerca de 8 GB).
   Ligue na tela Operação quando tiver espaço em disco.

O seu trabalho fica em **Revisões** (homônimos, divergências) e em **Leads** (aprovar,
descartar, confirmar contatos e registrar a prospecção). O sistema nunca envia mensagens.

Teste rápido da fila: em **Agentes e jobs**, clique em **Testar pipeline (ping)**.

Testes do backend: `cd backend && pytest -q` (usa o Postgres em `localhost:5432`).

## Usando o Supabase

1. Crie o projeto no Supabase.
2. Em `backend/.env`, use a connection string do projeto em `DATABASE_URL` e rode
   `python -m app.migrate` (ou `supabase db push`).
3. Crie um bucket **privado** chamado `rpi-originais` (Storage).
4. Backend: `AUTH_MODE=supabase`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
   e `STORAGE_BACKEND=supabase`.
5. Frontend: `NEXT_PUBLIC_SUPABASE_URL` e `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
6. Crie os usuários em Authentication > Users (não há cadastro público).

Todas as tabelas têm RLS ligado e nenhuma policy: a chave pública (anon) não lê nada.
Só o backend acessa o banco.
