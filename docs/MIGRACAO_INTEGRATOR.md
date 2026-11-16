# Migração do INPI Agent para a Integrator Host (Painel ICP)

Estado em 16/11/2026: **Parte 2, auditoria da origem**, feita a partir do código e da produção.

Nada foi alterado. O destino ainda não foi acessado.

## 1. Origem: o que existe hoje

| Componente | Onde | Função | Versão / imagem | Dados persistentes | Destino planejado |
|---|---|---|---|---|---|
| **api** | EasyPanel · projeto `evo`, serviço Compose `systeminpi` | FastAPI: API, autenticação, webhooks, regras comerciais. Na subida aplica as migrations | `python:3.12-slim`, porta 8000 | volume `dados` (RPIs originais, cache CNPJ) | Container `api` no ICP, `api.inpiagent.com.br` |
| **worker** | mesmo Compose | Fila em PostgreSQL e agendador | mesma imagem da api | volume `dados` | Container `worker`, **uma única instância** |
| **web** | mesmo Compose | Next.js 15.5 e React 19. Repassa `/api`, `/webhooks`, `/health` e `/ws` para a api | `node:22-alpine`, porta 3000 | — | Container `web`, `app.inpiagent.com.br` |
| **db** | mesmo Compose | PostgreSQL do sistema | `postgres:16` | volume `pgdata` | PostgreSQL 16 no ICP, sem porta pública |
| **inpi-evolution** | EasyPanel · App `inpi-evolution` | Evolution API exclusiva do INPI Agent, instância `inpi-agent` | `evoapicloud/evolution-api:latest` (2.3.7), cache local, sem Redis | volume `instances`, banco `inpi-evolution-db` | Evolution exclusiva no ICP. A sessão do WhatsApp pode exigir novo pareamento |
| **inpi-evolution-db** | EasyPanel · Postgres | Banco da Evolution do INPI | `postgres:18` | volume do serviço | Junto com a Evolution |
| `evolution-api`, `evolution-api-db`, `evolution-api-redis`, `kisabor-*` | mesmo projeto `evo` | **Outro negócio** | — | — | **Não migrar e não tocar** |

- **Redis:** o INPI Agent **não usa**. A fila é a tabela `jobs` no PostgreSQL, e a Evolution do INPI usa cache local.
- **Repositório:** `github.com/jsagencia04-coder/INPI-Lead-Intelligence`, branch `main`.
- **Commit publicado:** `95e480f` (V2.8).
- **Arquivo de infraestrutura:** `docker-compose.easypanel.yml`. Há também `docker-compose.prod.yml` (com Caddy e HTTPS próprio) e `docker-compose.yml` (desenvolvimento).

### Código

- **Migrations:** 18 arquivos SQL incrementais (`supabase/migrations`), da `…0001_init` à `…0018_modelos_mensagem_v27`. São aplicadas na subida da api, e a tabela de controle impede reaplicar.
- **API:** 113 rotas.
  - Autenticação local por token assinado (`APP_SECRET_KEY`) e papéis em `app_users`.
  - Webhooks públicos: `/webhooks/evolution/{instância}` (token na URL) e `/api/whatsapp/webhook` (Meta, desligada).
- **Agendamentos** (tabela `schedules`):
  - `rpi-descoberta` e `rpi-terca` (`rpi.discover`);
  - `operacao-semanal`;
  - `leads-montagem`;
  - `prazos-servicos`;
  - `inpi-verificacao`;
  - `pesquisa-gratuita` e `pesquisa-web`;
  - `receita-contatos`.
- **Integrações externas:**
  - revistas.inpi.gov.br (RPI);
  - busca.inpi.gov.br (pePI);
  - dados abertos da Receita (CNPJ);
  - sites das empresas (pesquisa);
  - Anthropic (opcional);
  - Evolution API.
- **Dependências do backend:**
  - fastapi, uvicorn e websockets;
  - psycopg 3 com pool;
  - pydantic e pydantic-settings;
  - PyJWT, httpx e python-multipart;
  - phonenumbers, dnspython e openpyxl.
- **Variáveis da origem** (só os nomes; os valores ficam no painel e não vão para o Git):
  - `POSTGRES_PASSWORD`, `APP_SECRET_KEY`, `APP_ENV`, `AUTH_MODE`;
  - `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD`;
  - `DOMINIO`;
  - `WHATSAPP_VERIFY_TOKEN`;
  - `MENSAGERIA_PROVEDOR`;
  - `EVOLUTION_BASE_URL`, `EVOLUTION_INSTANCE_NAME`, `EVOLUTION_API_KEY`, `EVOLUTION_WEBHOOK_TOKEN`;
  - `EVOLUTION_NUMERO_AUTORIZADO`, `EVOLUTION_SEND_ENABLED`, `EVOLUTION_SIMULATION`, `EVOLUTION_NUMEROS_TESTE`.

### Pendente na auditoria (precisa do EasyPanel logado)

A sessão do EasyPanel no navegador expirou. Para completar sem alterar nada, preciso medir:

- tamanho do banco e quantidade de linhas por tabela, que servem de base da comparação origem × destino;
- tamanho do volume `dados`;
- tamanho dos dados da Evolution;
- fila de jobs em andamento.

## 2. Pontos de atenção para o destino

1. **Um único worker.** O worker antigo precisa estar parado antes do novo subir, senão as tarefas da fila rodam duas vezes.
2. **Um único gravador.** No corte, a origem para de gravar (api e worker parados), faz o backup final, restaura no destino e só então o destino é ligado.
3. **WhatsApp.** A sessão do número 49 9 9978-9296 está no banco e no volume da Evolution do INPI. Duas Evolutions com a mesma sessão derrubam a conexão. Por isso:
   - ou a sessão migra com a Evolution da origem parada;
   - ou o número é pareado de novo no destino.

   Os dois casos exigem a sua confirmação. O envio real fica **desligado** durante toda a migração.
4. **Domínios.**
   - A web já repassa `/api` e `/webhooks` para a api, então `app.inpiagent.com.br` sozinho já atende tudo.
   - `api.inpiagent.com.br` e `webhooks.inpiagent.com.br` podem apontar para o container da api.
   - O webhook real fica em `https://webhooks.inpiagent.com.br/webhooks/evolution/inpi-agent?token=…`. O prefixo `/webhooks` é a rota do backend.
5. **Credenciais expostas antes, a rotacionar no destino:**
   - senha do painel;
   - `BOOTSTRAP_ADMIN_PASSWORD`;
   - chaves da Evolution;
   - `EVOLUTION_WEBHOOK_TOKEN`.
6. **Recursos.** O worker chegou a 100% de CPU lendo RPIs antigas, e a RPI de marcas tem cerca de 50 MB de XML. Para a carga atual, o mínimo recomendado é 2 vCPU e 4 GB de RAM; o disco depende do tamanho do volume `dados`, ainda a medir.

## 3. Sequência planejada

| Fase | O que | Depende de |
|---|---|---|
| A | Concluir a auditoria (tamanhos e contagens) | EasyPanel logado no navegador |
| B | Inspecionar a VPS: IP, sistema, Docker, CPU, RAM, disco, firewall, Painel ICP | Acesso ao Painel ICP e/ou SSH |
| C | Preparar o destino: rede interna, volumes, firewall (só 80/443/SSH), stack do INPI e Evolution exclusiva | B |
| D | Backup de ensaio da origem (pg_dump `-Fc` com checksum, arquivo do volume `dados`) e restauração no destino, sem parar a origem | C |
| E | Homologação no destino por IP ou domínio temporário, com envio desligado e worker do destino sem agendador | D |
| F | Registro de `inpiagent.com.br`, DNS (app, api, webhooks) e SSL | Domínio registrado por você |
| G | Corte em janela combinada: origem para de gravar, backup final, restauração, comparação de contagens, liga o destino, webhook | **Sua confirmação específica** |
| H | Origem mantida parada e intacta como contingência | — |

Rollback: o DNS volta para a origem e a origem é religada. Os dados gerados no destino ficam guardados para reconciliação. Nada é apagado.

## 4. Domínio definitivo (16/11/2026)

O domínio registrado foi **agentedemarcas.com.br** (Registro.br), e não inpiagent.com.br.

- **DNS:** servidores do Registro.br, em modo avançado.
  - `agentedemarcas.com.br` com registro A para 216.22.17.86 (VPS Integrator);
  - `www` é CNAME para o domínio principal.
- **Painel ICP:**
  - os dois nomes foram adicionados como alias do site 1, ao lado de `vps12823.panel.icontainer.work`;
  - o SSL foi emitido pelo fluxo coordenado do painel, com status "covered";
  - o proxy para o web (127.0.0.1:3100) é o mesmo.
- **Teste:** `https://agentedemarcas.com.br/health` e `https://www.agentedemarcas.com.br/login` respondem pelo destino.
- **Até o corte:** o domínio abre a **homologação**. A produção continua no EasyPanel.
- **No corte:** ajustar `DOMINIO` no `.env` do destino e o webhook da Evolution para `https://agentedemarcas.com.br/webhooks/evolution/inpi-agent?token=…`.

## 5. Corte realizado (16/11/2026, 22:45–22:56 UTC)

| Passo | Resultado |
|---|---|
| Origem em somente leitura | `alter database inpi set default_transaction_read_only = on`, conexões encerradas |
| Evolution | `pg_dump` (236 KB) e sessão (`/evolution/instances`, 1.750 arquivos) enviados com sha256 conferido. A Evolution da origem foi **parada** |
| Banco do INPI Agent | 49 tabelas, **1.290.707 linhas, sem divergências** |
| Arquivos | `dados.tar.gz` com 6,87 GB; sha256 conferido; 40 itens restaurados |
| Fila antiga | 22.875 jobs (`queued`/`running`) marcados como `cancelled`, a pedido do usuário. Nenhuma linha apagada |
| Evolution no ICP | `evoapicloud/evolution-api:v2.3.7` e `postgres:18`, só na rede interna. **Conectou com a sessão migrada** (wuid 554999789296), sem novo pareamento |
| Webhook | Interno, `http://api:8000/webhooks/evolution/inpi-agent?token=…`, com **token novo** e respondendo 200 |
| Worker | Ligado no ICP (`COMPOSE_PROFILES=evolution,corte`); é o único worker |
| Origem | Compose `systeminpi` e app `inpi-evolution` **parados, não apagados** |
| Limpeza | Receptor parado, token de migração revogado, `location /_migracao/` removida do nginx |

**Credenciais:**

- **Rotacionadas no corte:**
  - token do webhook;
  - chave global da Evolution;
  - senhas dos bancos;
  - `APP_SECRET_KEY` (por isso todos precisam fazer login de novo);
  - `WHATSAPP_VERIFY_TOKEN`.
- **Mantida:** a chave da instância (`EVOLUTION_API_KEY`), que veio da origem direto para o `.env` do destino, sem passar por log.
- **Pendente de rotação:** a senha do painel e o `BOOTSTRAP_ADMIN_PASSWORD` da origem.

**Configuração:** o envio continua como estava na produção:

- Evolution ligada;
- envio real só para os números de teste autorizados.

**Rollback:**

1. Parar o worker e a Evolution no ICP.
2. Na origem, iniciar o serviço `systeminpi` e executar `alter database inpi reset default_transaction_read_only`.
3. Iniciar a Evolution da origem.

Os dados gravados no ICP depois do corte ficam no ICP, para reconciliação.
