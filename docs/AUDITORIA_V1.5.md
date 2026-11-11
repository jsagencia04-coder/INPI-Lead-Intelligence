# INPI Lead Intelligence — Auditoria V1.5 e plano corretivo

Data: 11/11/2026 · Escopo: código da v1.5 (backend, frontend, migrations, agentes, fila, escritório, WhatsApp, autenticação, armazenamento).
Nada foi alterado nesta fase. Nenhum dado apagado, nada publicado.

## 0. Linha de base (executada nesta auditoria)

| Verificação | Resultado |
|---|---|
| Testes backend (pytest, Postgres 16 local) | 61 aprovados |
| Testes frontend (vitest) | 20 aprovados |
| Lint backend (ruff) | sem apontamentos |
| Typecheck frontend (tsc --noEmit) | sem erros |
| RLS ativo em todas as tabelas `public` | confirmado no banco de teste |

Não verificado (fora do alcance desta auditoria): a instalação na sua máquina (pasta D:), o layout real do PDF da RPI (preciso de um exemplar) e configuração de um Supabase de produção. Varredura de vulnerabilidades de dependências (pip-audit / npm audit) ainda não existe no projeto.

## 1. Problemas encontrados

### Críticos

| # | Problema | Onde | Impacto |
|---|---|---|---|
| C1 | Não existe separação de ambientes. `AUTH_MODE` tem padrão `dev`, e o `docker-compose.prod.yml` não o define: o modo "prod" local roda **sem login** (usuário fixo `dev@local`). | `config.py`, `docker-compose.prod.yml` | Qualquer pessoa que alcance a porta 3000 opera o sistema. |
| C2 | **SSRF**: o leitor de sites e a validação de contatos seguem redirecionamentos e acessam qualquer endereço, sem checar IP. As URLs vêm de páginas web e da IA. | `agents/site_crawler.py` (cliente httpx), `validation.py: fetch_page` | Uma página maliciosa pode levar o sistema a acessar `localhost`, a rede interna do Docker (`db:5432`, `api:8000`) ou metadados de nuvem (169.254.169.254). |
| C3 | Mensagem de WhatsApp afirma prazos ("60 dias") sem fonte e diz, na extinção, que **"a marca ficou sem proteção"** — sem consultar o estado atual (a LPI prevê prazo extraordinário de prorrogação após o fim da vigência). Não cita titular nem fonte. | `frontend/src/lib/whatsapp.ts` | Afirmação potencialmente falsa ao cliente; risco jurídico e de reputação. |
| C4 | Não há controle de permissões: todo usuário autenticado é administrador (aprova leads, altera classificação de despachos, agenda e dispara jobs, exporta). Se o cadastro do Supabase estiver aberto, qualquer pessoa vira administradora. | `auth.py`, todas as rotas | Escalada de privilégio. |

### Altos

| # | Problema | Onde |
|---|---|---|
| A1 | Importação de **PDF inexistente**: o sistema só baixa e guarda os PDFs (`RPI_DOWNLOAD_PDF`); não extrai nada. O upload aceita só `RM<N>.zip`. PyMuPDF não está instalado; OCR não existe. | `agents/rpi.py`, `api/rpi_routes.py` |
| A2 | Captura **não é integral**: o escopo padrão `alvo` só grava processos com despachos habilitados (7 códigos). Publicações dos demais despachos são descartadas. | `config.py: rpi_import_scope`, `rpi/importer.py` |
| A3 | Classificação de despachos é binária (`ativo_para_leads` + `revisar`). Não há os estados "relevante / não relevante / revisão / novo", nem a separação explícita processo → publicação → oportunidade → lead na interface. | `despacho_types`, tela Despachos |
| A4 | Domínios reservados não são bloqueados: há só um filtro de e-mail com `example.`. `.invalid`, `.test`, `.example`, `.localhost`, `example.com/.net/.org` e IPs literais passam. | `validation.py`, `site_crawler.py` |
| A5 | Validação fraca em dois casos: (a) e-mail vira `dominio_ok` com **MX + domínio igual ao site**, sem o e-mail aparecer em nenhuma página; (b) contato do tipo site vira `dominio_ok` porque o próprio domínio aparece na própria página (trivial). | `validation.py: check_contact` |
| A6 | A aprovação humana é do **lead**, não da **mensagem**. O texto efetivamente enviado não é registrado; a mensagem pode ser editada sem nova aprovação. | `whatsapp-card.tsx`, `outreach_log` |

### Médios

| # | Problema | Onde |
|---|---|---|
| M1 | Dados de demonstração não têm barreira no banco. O modo demo do escritório é só visual (correto), mas nada impede gravar contato fictício em produção. Na v1.5, o print do lead usou um contato `.invalid` gravado no banco **de desenvolvimento** desta sessão. | banco |
| M2 | `reports.weekly` **apaga** `agent_events` com mais de 30 dias — conflita com "não apagar dados". | `agents/leads.py` |
| M3 | Token do WebSocket vai na URL (`/ws/office?token=`), e URLs aparecem em logs de proxy. | `office_routes.py`, `use-real.ts` |
| M4 | Erro de JWT devolve o detalhe da exceção ao cliente. | `auth.py` |
| M5 | Tabelas sem gatilho de auditoria: `publications`, `lead_processes`, `research_runs`, `reports`, `exports_log`, `llm_calls`. | migrations |
| M6 | Senha fixa `postgres` no compose de produção; nenhuma checagem de segredos padrão ao iniciar. | `docker-compose.prod.yml` |
| M7 | Upload lê até 200 MB inteiro na memória. | `rpi_routes.py: upload` |
| M8 | CI sem pip-audit / npm audit. | `.github/workflows/ci.yml` |

### O que está correto e será preservado
Originais imutáveis com SHA-256 único; fila com dedupe e backoff; auditoria por gatilho na maioria das tabelas; RLS em todas as tabelas; pePI respeitando CAPTCHA (pausa, nunca resolve); opt-out por hash (LGPD); prospecção exige lead aprovado e contato fora do opt-out; nenhum envio automático; escritório virtual (não será substituído).

## 2. Plano corretivo

Ordem proposta: **segurança e ambientes primeiro** (fases 4 e 5), porque as fases 2 e 3 aumentam muito o volume de dados externos processados.

### Etapa A — Ambientes e dados reais (Fase 4)
- `APP_ENV = demo | homologacao | producao` (migration 0007 registra o ambiente do banco; API recusa iniciar se o banco for de outro ambiente).
- Checagem de inicialização em homologação/produção: exige `AUTH_MODE=supabase`, recusa senha padrão do banco, CORS explícito, chave de API só no backend.
- Bloqueio de dados fictícios: função única `dominio_reservado()` (RFC 2606/6761 + IPs literais) usada no backend **e** em gatilho do banco nas tabelas `contacts` e `evidences` quando o ambiente for produção.
- Validação: "validado" exige evidência verificável (URL + SHA-256 da página + valor reencontrado). Formato e MX sozinhos ficam em `formato_ok`. Contatos existentes são **reavaliados por job** (rebaixamentos ficam na auditoria; nada é apagado).

### Etapa B — Segurança (Fase 5)
- `net_guard`: só http/https nas portas 80/443; resolve DNS e rejeita IP privado, loopback, link-local, CGNAT, multicast e reservado; redirecionamentos seguidos manualmente (máx. 5), revalidando cada salto; limite de tamanho de resposta. Aplicado ao crawler, à validação e aos downloads.
- Papéis: `admin`, `revisor`, `operador`, `leitor` (tabela `app_users` + primeiro admin via `BOOTSTRAP_ADMIN_EMAIL`). Matriz de permissões por rota; e-mail fora da lista = acesso negado.
- WebSocket autentica na primeira mensagem (sem token na URL); erros de JWT genéricos.
- Auditoria nas tabelas que faltam; acessos a exportação e download de originais registrados.
- Limpeza de `agent_events` desligada (vira arquivamento opcional, desligado por padrão).

### Etapa C — Importação de PDF (Fase 2)
- Upload de PDF (Volume I e II), gravado em disco por streaming; original imutável + SHA-256; duplicidade: mesmo hash = reaproveita; mesma edição/volume com hash diferente = tarefa de revisão (nunca sobrescreve).
- Extração com PyMuPDF por página; OCR (Tesseract, português) só nas páginas sem camada de texto. Cada publicação guarda arquivo e **página de origem**.
- Comparação opcional com o XML oficial da mesma edição: relatório de divergências (processos/despachos só no PDF, só no XML, diferentes).
- `RM.zip` continua funcionando como hoje.
- **Necessário:** um PDF real (de preferência os volumes da RPI 2914, para comparar com o XML que já temos nos testes).

### Etapa D — Todos os despachos (Fase 3)
- Escopo padrão `todos`: todo processo e toda publicação ficam gravados.
- Classificação configurável: `relevante`, `nao_relevante`, `revisao`, `novo` (despacho nunca visto entra como `novo`). Migração converte a configuração atual sem perder nada.
- Funil explícito: processo importado → publicação identificada → oportunidade (publicação relevante + sem procurador) → lead qualificado (titular identificado + revisão humana). Contadores de cada camada no dashboard.
- Estimativa de volume antes de ligar (Supabase gratuito tem 500 MB).

### Etapa E — Prospecção (Fase 6)
- Mensagens só com fatos e fonte: número do processo, marca, titular, despacho (texto oficial e código), RPI e data oficial, link da fonte.
- Sem prazos legais na mensagem por padrão. Sem "perdeu proteção": na extinção, só o despacho publicado e, se houver consulta ao INPI, o estado atual com a data da consulta.
- Rascunho → aprovação humana → envio manual: o texto aprovado fica gravado (com hash); editar depois exige nova aprovação; o registro da prospecção aponta para o texto aprovado.

### Etapa F — Testes e documentação (Fase 7)
Unitários, integração, segurança (SSRF com DNS apontando para IP interno, redirecionamento para localhost, rotas sem papel, produção sem auth), importação (PDF texto, PDF com OCR, duplicidade, comparação com XML), deduplicação, WhatsApp, escritório, build de produção e build Docker; pip-audit e npm audit no CI. Documentação atualizada. Só declaro aprovado o que for executado.

## 3. Riscos e pendências
- **Layout do PDF**: o parser depende de um exemplar real; sem ele, a Etapa C fica bloqueada.
- **DNS rebinding**: a validação por IP antes da conexão reduz, mas não elimina; risco residual documentado.
- **Volume**: captura integral pode exigir plano pago do Supabase.
- **Reavaliação de contatos**: alguns contatos hoje "validados" podem cair para `formato_ok` com as regras novas.
- Não sei se a correção da senha do banco funcionou na sua máquina.
