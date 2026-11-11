# INPI Lead Intelligence V2.0 — Sales Engine

Estado em 11/11/2026. Entrega em etapas, conforme a Fase 13 do escopo.

| Etapa (Fase 13) | Situação |
|---|---|
| 1. Auditar a versão existente | Feita (este documento + `AUDITORIA_V1.5.md`) |
| 2. Apresentar as migrations | Feita (seção 2) |
| 3. Central de contatos | **Implementada e testada** (seção 3) |
| 4. Autorização e pipeline | Pendente (estrutura de consentimentos já criada) |
| 5. API oficial do WhatsApp | **Implementada e testada com a Meta simulada** (ver `WHATSAPP_API.md`); envio real restrito a números de homologação e a login obrigatório |
| Segurança (Fase 12) | **Implementada e testada** (ver `SEGURANCA.md`): login próprio, perfis, ambientes, SSRF, dados fictícios, limite de taxa |
| 6. Testes em homologação | Pendente |

Nenhum disparo foi feito. Nenhum dado foi apagado. Nada foi publicado.

## 1. Auditoria da versão existente frente ao escopo V2.0

### 1.1 O que já existe e foi preservado

| Fase V2.0 | Já existe | Falta |
|---|---|---|
| 2 WhatsApp | Busca de `wa.me` / `api.whatsapp.com` / rótulo "WhatsApp" nos sites; 3 níveis | Níveis FOUND…INVALID em campos independentes → **feito na 0007** |
| 3 Pesquisa gratuita | `research.free` com robots.txt, pausa, vínculo com o titular, 6 páginas/domínio | Métricas de cobertura; mais fontes de domínio; mais páginas de contato |
| 4 Base CNPJ | `cnpj.sync` lê o tamanho remoto e reaproveita arquivos já baixados | Checagem de espaço em disco **antes** do download; progresso; histórico; confirmação |
| 5 Pesquisa com IA | Sem chave: `research.batch`/`research.holder` retornam sem chamar a IA nem gastar; orçamento semanal | O agendamento ainda cria um job vazio a cada ciclo; falta status "aguardando configuração" e limite de pesquisas configurável na tela |
| 6 Pipeline | Status de lead com 9 estados | Pipeline de 17 etapas + histórico da jornada |
| 7 WhatsApp API | Nada (só link `wa.me` manual) | Tudo |
| 8 Consentimento | `suppression_list` (opt-out por hash) | Tabela `consents` → **criada na 0008**; fluxo de solicitação; opt-out por palavra-chave |
| 9 Campanha | Nada | Tudo |
| 10 Sales Closer | Nada | Tudo |
| 11 Dashboard comercial | Dashboard operacional | Indicadores comerciais |
| 12 Segurança | Auditoria por gatilho, RLS, opt-out | Ver 1.2 |

### 1.2 Bloqueios antes de qualquer envio automático

Vêm da auditoria V1.5 e continuam abertos. **A integração com a API do WhatsApp (etapa 5) não deve ser ligada antes de resolvê-los:**

1. **Sem login no modo Docker atual** (`AUTH_MODE` padrão `dev`). Com envio automático, quem alcançar a porta 3000 dispararia mensagens.
2. **Sem níveis de permissão**: todo usuário é administrador. Aprovar campanha precisa ser um papel separado.
3. **SSRF** no leitor de sites e na validação de contatos.
4. **Sem separação demo / homologação / produção** e sem bloqueio de domínios de exemplo.
5. **Mensagens atuais afirmam prazos e "perdeu proteção"** sem fonte.

### 1.3 Ponto de atenção do próprio escopo (Fase 8 × Fase 9)

A regra da Fase 8 está correta e é restritiva: só envia quando **o destinatário forneceu o número e autorizou**. Um número encontrado em site público **não** cumpre isso. Consequência prática: no primeiro dia, a campanha FIRST CONTACT terá **zero** destinatários elegíveis. A elegibilidade nasce de (a) pedido de autorização por outro canal (e-mail), (b) contato iniciado pelo próprio titular, ou (c) contato manual seu, um a um, que resulte em autorização registrada. O sistema vai seguir essa regra à risca; ele não a contorna.

## 2. Migrations

Todas incrementais (só acrescentam). Nenhuma apaga ou reescreve dados.

| Nº | Arquivo | Conteúdo | Situação |
|---|---|---|---|
| 0007 | `20261112000007_central_contatos.sql` | `contacts`: `eh_celular`, `wa_nivel`, `wa_conta`, `wa_comercial`; gatilho que deriva o nível do que o pipeline já grava; preenchimento dos contatos existentes | **Aplicada e testada** (inclusive sobre dados pré-existentes) |
| 0008 | `20261112000008_consentimentos.sql` | Tabela `consents` (todos os campos da Fase 8; não permite apagar, só revogar; auditoria; RLS); view `v_contact_central` | **Aplicada e testada** |
| 0010 | `20261112000010_seguranca.sql` | `app_config` (ambiente do banco), `app_users` (perfis; auditoria sem hash de senha), bloqueio de domínios fictícios fora do demo, auditoria nas tabelas que faltavam | **Aplicada e testada** |
| 0011 | `…_pipeline_comercial.sql` | `leads.pipeline_stage` (17 etapas, convertidas dos 9 status atuais sem perda), `lead_stage_history` (jornada, imutável) | Proposta |
| 0009 | `20261112000009_whatsapp_api.sql` | `wa_messages` (chave de idempotência única, id da Meta, status só vindos do webhook), `wa_webhook_events` (bruto, imutável, dedupe), `suppression_list.origem` | **Aplicada e testada** |
| 0012 | `…_campanhas.sql` | `campaigns` (modo simulação / revisão / automático; aprovação), `campaign_recipients` (único por campanha+contato+processo), motivo de inelegibilidade | Proposta |
| 0013 | `…_sales_closer.sql` | `reply_classifications`, `suggested_replies` (sempre pendentes de aprovação humana), `deals` (reunião, proposta, valor) | Proposta |
| 0014 | `…_metricas.sql` | `research_metrics` (Fase 3), `cnpj_sync_runs` (Fase 4), view `v_dashboard_comercial` (Fase 11) | Proposta |

## 3. Central de contatos (implementada)

**Tela** `/contatos` (menu "Central de contatos"): uma linha por titular com razão social, nome fantasia, CNPJ, marcas, processos e o melhor WhatsApp, telefone, e-mail, site, Instagram e LinkedIn — cada um com status e origem clicável. A seta abre todos os contatos do titular com confiança, data, origem e o trecho da fonte.

- **13 filtros** com contador: todos, somente WhatsApp, WhatsApp candidatos, com evidência empresarial, confirmado manualmente, telefones, e-mails, sem contatos, pendentes, inválidos, leads aprovados, com permissão, bloqueados.
- **Busca** por nome (titular, razão social, fantasia), CNPJ, marca e número do processo.
- **Ordenação** (titular, data da pesquisa, confiança, score, nº de contatos), **paginação** (50 por página), **exportação** Excel e CSV (registrada em `exports_log`).
- **Sem duplicidade**: unicidade por titular + tipo + valor normalizado (já existia; agora coberta por teste).

**Níveis de WhatsApp** (`contacts.wa_nivel`): `found`, `candidate`, `company_evidence`, `human_confirmed`, `invalid`.
Campos independentes: `eh_celular` (formato), `wa_conta` (conta existe — só pessoa confirma), `wa_comercial` (é o canal comercial da empresa), e autorização (tabela `consents`). O opt-out prevalece sobre qualquer consentimento.

**API** (somente leitura): `GET /api/contact-central`, `/api/contact-central/counts`, `/api/contact-central/export`.

### Arquivos
Novos: as duas migrations; `backend/app/api/contact_routes.py`; `backend/tests/test_central_contatos.py`; `frontend/src/app/contatos/page.tsx`; `frontend/src/lib/contatos.ts`; `frontend/src/lib/contatos.test.ts`; este documento.
Alterados: `backend/app/main.py` (registra a rota); `frontend/src/components/sidebar.tsx` (item de menu); `backend/tests/conftest.py` e `test_api.py` (nova tabela / nome da última migration).
Nenhum agente, rota ou tela existente foi modificado.

### Testes executados em 11/11/2026

| Verificação | Resultado |
|---|---|
| Backend (pytest) | 67 aprovados (61 anteriores + 6 novos) |
| Frontend (vitest) | 24 aprovados (20 anteriores + 4 novos) |
| Lint backend (ruff), typecheck (tsc), lint da tela nova (eslint) | sem apontamentos |
| Build de produção (next build) | concluído |
| Migration sobre banco com dados anteriores (0001–0006 + contatos, depois 0007–0008) | contatos preservados e classificados |
| Tela aberta no navegador com dados de teste | conferida |

Não executados: build das imagens Docker; testes na sua máquina; testes com dados reais do INPI.

### Pendências desta etapa
- "Com permissão de comunicação" fica vazio até existir o fluxo de registro de consentimento (etapa 4).
- Diretórios empresariais públicos como fonte (Fase 2, item 7): ainda não implementado.
- Com dezenas de milhares de titulares a view pode precisar virar tabela materializada.
