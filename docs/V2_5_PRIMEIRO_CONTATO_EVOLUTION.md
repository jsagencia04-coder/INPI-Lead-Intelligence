# V2.5 — Primeiro contato supervisionado com a Evolution API

Estado em 13/11/2026.

| Item | Situação |
|---|---|
| Código | Implementado e testado em simulação: 175 testes do backend aprovados, 14 deles novos |
| Produção | **Não publicado** |
| Instância `inpi-agent` | **Ainda não criada** (passo seu, abaixo) |
| Envio real | **Nenhum envio real foi feito** |

## 1. Diagnóstico da infraestrutura (Fase 1)

| Item | Encontrado |
|---|---|
| Evolution API | Serviço `evolution-api` (App) do projeto **evo** no EasyPanel, imagem `evoapicloud/evolution-api:latest` |
| Versão | **2.3.7**, conector WhatsApp Web (Baileys) 2.3000, `clientName=evolution_exchange` |
| Persistência | PostgreSQL próprio (`evolution-api-db`) e Redis próprio (`evolution-api-redis`); `DEL_INSTANCE=false` |
| Histórico | `DATABASE_SAVE_DATA_HISTORIC=true`: ao criar a instância, desligue a sincronização do histórico completo |
| Endereços | Interno `http://evo_evolution-api:8080`; público `https://evo-evolution-api.301ow2.easypanel.host` (o /manager também é público; isso já existia) |
| Outros serviços do projeto | `kisabor-gateway` e `kisabor-redis` (o outro negócio). Nada foi tocado. |
| Rede | O INPI Agent (compose) **não resolve** o nome interno da Evolution; o **HTTPS público funciona** (testado de dentro do worker, só na rota pública de boas-vindas, sem credencial) |
| Recursos | Evolution com cerca de 175 MB de memória; o INPI Agent chegou a 100% de CPU durante a leitura das RPIs antigas |

**Decisões tomadas com você:**

- conector por QR Code (Baileys), com o risco registrado abaixo;
- comunicação pelo HTTPS público;
- a instância é criada por você no Evolution Manager, de modo que a chave global do outro negócio nunca passa pelo sistema nem por mim.

**Risco aceito:** o conector por QR Code usa o protocolo do WhatsApp Web, que não é a API oficial. Isso contraria os termos do WhatsApp e a regra que você havia definido antes. O número pode ser bloqueado, mesmo com poucos envios autorizados. Mitigações já no sistema:

- um envio por titular, sempre com aprovação humana e autorização do destinatário;
- sem envio em massa, sem follow-up e sem resposta automática;
- sem proxies nem rotação de números.

## 2. O que foi implementado

- **Um provedor por vez:** `MENSAGERIA_PROVEDOR` = `manual` (padrão), `evolution` ou `meta`. Com a Evolution selecionada, a Cloud API da Meta não envia nem processa webhooks.
- **Rascunho:**
  - gerado pela IA (ou por um modelo fixo, sem chave da Anthropic) usando só dados verificados do processo;
  - edição livre;
  - texto com lacuna `[seu nome]` não pode ser aprovado.
- **Aprovação:**
  - só revisor ou admin aprova;
  - a aprovação fica presa ao texto, ao número, ao canal e à versão;
  - qualquer mudança invalida a aprovação;
  - aprovar uma versão que já mudou na tela de outra pessoa é recusado.
- **Verificações no backend antes de enviar.** Negar é o padrão:
  - provedor;
  - botão de emergência;
  - aprovação válida;
  - número igual ao do contato;
  - contato validado;
  - número fornecido pelo destinatário;
  - autorização ativa (tabela `consents`);
  - fora do opt-out;
  - lead aprovado;
  - nenhum envio anterior ao contato;
  - permissão do usuário;
  - instância conectada;
  - número remetente igual a `EVOLUTION_NUMERO_AUTORIZADO`;
  - número na lista de teste (quando definida).
- **Envio:**
  - o worker confere tudo de novo e faz **uma** chamada (`POST /message/sendText/inpi-agent`);
  - falha de conexão = não enviado;
  - tempo esgotado, erro 5xx ou resposta sem id = **"conferir no celular"**, sem reenvio automático;
  - a mensagem é marcada como "em andamento" antes da chamada; se o worker cair no meio, ela nunca sai duas vezes.
- **Webhook exclusivo** `POST /webhooks/evolution/inpi-agent?token=...`:
  - exige token e a instância certa;
  - aceita no máximo 256 KB e descarta eventos repetidos;
  - limita a taxa por IP;
  - atualiza a conexão e o status (enviada, entregue, lida);
  - quando um contato abordado responde, marca "respondeu" **sem guardar o texto** e aplica opt-out se a pessoa escrever SAIR;
  - conversas de outros números são ignoradas e não são gravadas;
  - nunca responde nada.
- **Abrir no WhatsApp:** link wa.me com o texto. Não marca como enviado.
- **Telas:**
  - **Comercial → Primeiro contato**: lista, dados do lead, origem do telefone, autorização, mensagem, requisitos e histórico;
  - **Comercial → Integração WhatsApp**: provedor, instância, número, conexão, simulação, envio, contadores, Testar conexão (não envia) e Desativar envios (emergência imediata; reativar só o admin).
- **Banco** (migration `20261116000016_primeiro_contato_evolution.sql`, incremental):
  - tabelas `wa_contas`, `wa_rascunhos` e `wa_auditoria`;
  - `wa_messages` ganha provedor, instância, rascunho e o status `reconciliar`;
  - `wa_webhook_events` ganha o provedor;
  - registro `whatsapp_envio_bloqueado` em `app_config`;
  - autorização e opt-out reaproveitam `consents` e `suppression_list`.
- **Segurança na subida:** fora do modo demo, a API não sobe com envio real sem login, sem o número autorizado ou com token do webhook menor que 24 caracteres.

## 3. Testes em simulação (`backend/tests/test_primeiro_contato.py`)

A Evolution é simulada e nada sai. O lead é real (944040470 TELEVAULT); o contato e a autorização são fictícios.

| # | Cenário | Resultado |
|---|---|---|
| 1 | Geração | Texto com marca, processo, prazo e linha SAIR |
| 2 | Edição | Nova versão, novo hash |
| 3 | Rejeição | Não envia |
| 4 | Aprovação | Só revisor ou admin |
| 5 | Alteração após aprovação | Aprovação cai |
| 6 | Sem autorização | Bloqueado |
| 7 | Opt-out | Bloqueado e autorização revogada |
| 8 | Duplicidade | Segundo envio bloqueado (primeiro contato é único) |
| 9 | Falha de conexão | Não enviado, sem nova tentativa |
| 10 | Sem credenciais | Só simulação |
| 11 | Chave recusada | Bloqueado antes de enviar |
| 12 | Resposta sem id | "Conferir no celular" |
| 13 | Tempo esgotado ou 5xx | "Conferir no celular", sem reenvio |
| 14 | Dois operadores ao mesmo tempo | Edição e aprovação de versão velha recusadas; um só envio |
| 15 | Histórico | Ações em `wa_auditoria` e na auditoria por tabela |
| 16 | Isolamento | Outro número conectado bloqueia; webhook de outra instância é recusado; só a instância `inpi-agent` é chamada |
| 17 | Worker reinicia no meio | Não reenvia |
| 18 | Webhook | Status, resposta sem texto, número desconhecido ignorado, deduplicação, conexão |
| 19 | Desativar envios | Fila cancelada, envio recusado |
| 20 | Respostas automáticas | Nenhuma (contador de envios não muda) |

Também cobertos: simulação versus real; a Meta fica desligada; o link wa.me não conta como envio; a configuração insegura impede a API de subir.

**Resultado:** backend com 175 testes aprovados; frontend com 34 testes, lint e build sem problemas.

## 4. Passos seus, nesta ordem

1. **No Evolution Manager** (`https://evo-evolution-api.301ow2.easypanel.host/manager`), crie a instância **`inpi-agent`**:
   - integração WHATSAPP-BAILEYS;
   - **desligue** "sincronizar histórico completo";
   - **não** ative Chatwoot, Typebot, OpenAI ou outras automações;
   - **não** mexa na instância do outro negócio.
2. Leia o QR Code **com o celular do número do INPI Agent** (+55 49 3191-3301), em WhatsApp Business → Dispositivos conectados.
3. Copie o **token da instância** (não a chave global).
4. No EasyPanel, em **systeminpi → Environment**, acrescente as variáveis abaixo e clique em Deploy. Só o INPI Agent reinicia.

```
MENSAGERIA_PROVEDOR=evolution
EVOLUTION_BASE_URL=https://evo-evolution-api.301ow2.easypanel.host
EVOLUTION_INSTANCE_NAME=inpi-agent
EVOLUTION_API_KEY=<token da instância>
EVOLUTION_WEBHOOK_TOKEN=<segredo aleatório de 32+ caracteres>
EVOLUTION_NUMERO_AUTORIZADO=+554931913301
EVOLUTION_SEND_ENABLED=false
EVOLUTION_SIMULATION=true
PRIMEIRO_CONTATO_REMETENTE=<como você se apresenta>
```

5. Na instância, em **Webhook**, cadastre:
   - a URL `https://inpi.2.24.197.49.sslip.io/webhooks/evolution/inpi-agent?token=<EVOLUTION_WEBHOOK_TOKEN>`;
   - os eventos CONNECTION_UPDATE, MESSAGES_UPSERT, MESSAGES_UPDATE e SEND_MESSAGE.
6. No INPI Agent, em **Integração WhatsApp → Testar conexão**, o resultado deve ser "Conectado" e o número deve conferir.
7. **Teste real controlado** (Fase 12), só com sua autorização expressa:
   - `EVOLUTION_NUMEROS_TESTE=<seu número pessoal>`, `EVOLUTION_SIMULATION=false` e `EVOLUTION_SEND_ENABLED=true`;
   - faça um único envio para o seu próprio número, com a autorização registrada;
   - responda pelo celular e confira que nada respondeu automaticamente;
   - depois, volte `EVOLUTION_SEND_ENABLED=false`.

**Nunca teste com leads do INPI que não autorizaram o contato.**

## 5. Recuperação

| Situação | O que fazer |
|---|---|
| Parar tudo na hora | Botão **Desativar envios** (sem redeploy) ou `EVOLUTION_SEND_ENABLED=false` |
| Voltar ao modo manual | `MENSAGERIA_PROVEDOR=manual` |
| Remover a integração | Apague a instância `inpi-agent` no Manager. A do outro negócio não é afetada. |
| Desfazer a migration | Ela só cria tabelas e colunas. Desfazer seria apagar `wa_rascunhos`, `wa_contas`, `wa_auditoria` e as colunas novas, o que perde o histórico. **Não recomendado.** Desligar pelas variáveis basta. |

## 6. Pendências

- Criar a instância, ler o QR Code e configurar as variáveis e o webhook (seção 4).
- O teste real controlado só acontece depois da sua autorização.
- Rotacionar a senha do painel EasyPanel que ficou exposta antes de entrar em produção (recomendação anterior).
- Opcional: comunicação pela rede interna, depois de validar que o compose aceita a rede do EasyPanel.
