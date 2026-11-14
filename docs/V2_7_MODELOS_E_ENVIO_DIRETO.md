# V2.7: três modelos de mensagem e envio direto pela Evolution

Estado em 14/11/2026.

| Item | Situação |
|---|---|
| Código | Backend com 202 testes aprovados, sendo 11 novos e 14 da V2.5 ajustados. Frontend com 34 testes; lint, tipos e build sem problemas |
| Produção | **Não publicado** (aguardando autorização) |
| Envio real | Nenhum. Os testes usam a Evolution simulada |

## 1. O que muda para o operador

1. **Abrir o lead.** Nos detalhes do lead (`/leads/{id}`) há a seção **Primeiro contato pelo WhatsApp**. A mesma tela continua em Comercial → Primeiro contato.
2. **Escolher o modelo.** O sistema sugere o modelo pela oportunidade:
   - oposição → Modelo 01;
   - indeferimento → Modelo 02;
   - outros casos → Modelo 03.

   O operador pode escolher outro modelo **ativo e compatível**. O Modelo 03 serve para qualquer caso; o 01 e o 02 só para a própria finalidade.
3. **Preparar.** As variáveis são preenchidas só com dados verdadeiros. Quando falta algum dado, o sistema mostra um alerta e deixa uma lacuna entre colchetes (ex.: `[marca]`). A aprovação fica bloqueada até alguém preencher.
4. **Aprovar.** A aprovação vale só para estes seis itens, todos juntos:
   - texto exato;
   - destinatário;
   - canal;
   - versão;
   - modelo;
   - finalidade.

   Qualquer mudança exige nova aprovação. Se o consentimento for revogado, o envio é bloqueado.
5. **ENVIAR MENSAGEM.** O backend valida tudo e chama a Evolution **na mesma requisição**. A tela não abre guia, `wa.me` nem WhatsApp Web. O botão mostra o andamento:
   - "Aguardando envio..." e "Enviando mensagem...";
   - "Mensagem aceita pelo provedor";
   - "Mensagem entregue", só depois do evento de entrega do WhatsApp (a tela consulta a cada 3 s);
   - "Falha no envio" ou "Resultado incerto: confira no celular".

   O botão fica travado enquanto o envio está em andamento. Cada clique leva uma chave de idempotência: repetir o mesmo clique devolve o mesmo envio. Em caso de tempo esgotado, nada é reenviado sozinho.

## 2. Configurações de mensagens

Comercial → **Configurações de mensagens** (`/configuracoes-mensagens`).

- **Os três modelos ficam no PostgreSQL** (tabela `wa_modelos`), não no código. Cada um tem:
  - nome, identificação e descrição;
  - texto editável;
  - ativo ou inativo;
  - tipo de oportunidade;
  - data e usuário da última alteração;
  - botões de pré-visualização, salvar e testar prévia;
  - histórico de versões (`wa_modelos_historico`, que não pode ser alterado).
- **Remetente:** "Seu nome" (`{{nome_atendente}}`) e "Sua empresa" (`{{empresa}}`) também são editados nesta tela, sem publicar versão.
- **Ao salvar**, o sistema recusa:
  - uma versão desatualizada (duas pessoas editando ao mesmo tempo);
  - variáveis desconhecidas;
  - um texto sem a opção de descadastro (SAIR).
- **A prévia** usa dados de exemplo, marcados como tal, ou um lead real. Não grava nada e não envia nada.

### Variáveis

| Variável | Origem |
|---|---|
| `{{nome_titular}}` | Titular, como publicado na RPI |
| `{{marca}}` | Nome da marca (muitas notificações de oposição na RPI não trazem a marca: gera alerta e lacuna) |
| `{{numero_processo}}` | Processo da oportunidade |
| `{{tipo_despacho}}` | Notificação de oposição, indeferimento ou deferimento parcial |
| `{{edicao_rpi}}` | Número da RPI |
| `{{estado}}` | UF do titular, por extenso |
| `{{empresa}}` e `{{nome_atendente}}` | Configurados na tela |

**A mensagem personalizada é uma versão independente.** Ela fica no rascunho com:

- o modelo e a versão do modelo;
- o texto do modelo naquele momento;
- os valores usados;
- os alertas.

Editar o modelo depois não altera mensagens já preparadas.

## 3. Segurança comercial

Envio só com tudo isto conferido:

- provedor;
- botão de emergência;
- aprovação válida;
- número do contato;
- contato validado;
- número fornecido pelo destinatário;
- autorização ativa;
- fora do opt-out;
- lead aprovado;
- nenhum envio anterior ao contato;
- modelo ativo;
- texto sem lacunas;
- **no máximo 3 tentativas por mensagem** (só depois de falha definitiva);
- usuário revisor ou administrador;
- instância conectada;
- número remetente autorizado;
- lista de teste;
- **limite diário de 20 primeiros contatos** (`whatsapp_limite_diario`, ajustável no banco).

Não existe rotação de modelos, sorteio, variação artificial, intervalo aleatório, envio em massa nem reenvio automático.

## 4. Respostas

O webhook exclusivo da instância já registrava cada resposta e marcava o lead como "resposta recebida", sem guardar o texto e sem responder. Agora também:

- aparece um **aviso de respostas novas** em Primeiro contato, com o botão "Marcar como vistas";
- o sistema não responde e não inicia novo contato. A conversa continua no WhatsApp Business do celular.

## 5. Arquivos

### Banco

Migration `20261118000018_modelos_mensagem_v27.sql`:

- `wa_modelos`, com os 3 modelos iniciais;
- `wa_modelos_historico`;
- configurações `primeiro_contato_atendente`, `primeiro_contato_empresa` e `whatsapp_limite_diario`;
- em `wa_rascunhos`, novas colunas: `modelo_id`, `modelo_versao`, `modelo_texto`, `finalidade`, `variaveis` e `alertas`;
- em `wa_messages`, novas colunas: `modelo_id` e `visto_em`.

### Backend

- **`app/modelos.py`** (novo): leitura e salvamento dos modelos, substituição segura de variáveis, sugestão e compatibilidade do modelo.
- **`app/primeiro_contato.py`:**
  - o rascunho passa a vir do modelo, sem texto fixo no código e sem IA;
  - aprovação presa a modelo e finalidade;
  - novas verificações: modelo ativo, lacunas, limite de tentativas e limite diário;
  - chave de idempotência no envio.
- **`app/api/primeiro_contato_routes.py`:**
  - `POST /api/rascunhos/{id}/enviar` com `{chave}`: envio síncrono pelo backend;
  - `GET /api/wa-mensagens/{id}`: situação do envio;
  - `GET /api/primeiro-contato-respostas` e `POST /api/primeiro-contato-respostas/vistas`;
  - `GET /api/wa-modelos`, `PUT /api/wa-modelos/{codigo}` (administrador), `GET /api/wa-modelos/{codigo}/historico` e `POST /api/wa-modelos/{codigo}/previa`;
  - `PUT /api/wa-modelos-remetente` (administrador);
  - o detalhe do lead passa a trazer os modelos, o sugerido e o histórico completo dos envios.
- **`app/security.py`:** permissões das novas rotas.

### Frontend

- `components/primeiro-contato-painel.tsx` (novo): painel de revisão e envio, usado em Primeiro contato e nos detalhes do lead.
- `app/configuracoes-mensagens/page.tsx` (novo).
- `app/primeiro-contato/page.tsx`: usa o painel e mostra o aviso de respostas.
- `app/leads/[id]/page.tsx`: nova seção de primeiro contato.
- `lib/nav.ts`: novo item no menu.

**"Abrir no WhatsApp" (wa.me)** só aparece no modo manual, quando o provedor não é a Evolution.

## 6. Testes (`backend/tests/test_modelos_v27.py`, Evolution simulada)

| # | Teste | Resultado |
|---|---|---|
| 1, 2 | Edição dos 3 modelos no PostgreSQL, histórico de versões, versão desatualizada, variável desconhecida e texto sem SAIR recusados | Aprovado |
| 3 | Substituição segura: nada de "None", lacuna e alerta quando falta dado | Aprovado |
| 4, 5 | Sugestão por despacho, escolha manual compatível, modelo de outra finalidade e modelo inativo recusados | Aprovado |
| 6, 9 | Aprovação presa a modelo e finalidade; modelo desativado depois bloqueia o envio | Aprovado |
| 7, 8 | Envio simulado; envio real só para o número de teste autorizado | Aprovado |
| 10, 11 | Status "aceita" na resposta; "entregue" só com o evento do webhook | Aprovado |
| 12, 17 | Clique repetido devolve o mesmo envio; outro clique para o mesmo contato é bloqueado | Aprovado |
| 13, 14 | Sem consentimento bloqueia (o opt-out continua coberto pelos testes da V2.5) | Aprovado |
| 15, 16 | Falha de conexão e tempo esgotado sem reenvio | Aprovado |
| — | Limite diário | Aprovado |
| 18 | Histórico com modelo, texto, aprovador e id do provedor | Aprovado |
| 19, 20 | Resposta gera aviso; nenhuma resposta automática nem novo contato | Aprovado |

**Teste de tela** (navegador automatizado, ambiente local em simulação):

- o botão passou de "Enviar mensagem" para "Enviando mensagem..." e depois "Envio simulado (nada saiu)";
- **nenhuma página nova** foi aberta e não houve acesso a wa.me ou WhatsApp Web;
- a URL não mudou.

## 7. Pendências

- Publicar, depois da sua autorização.
- Preencher em Configurações de mensagens o **seu nome** e a **sua empresa**. Sem eles, toda mensagem fica com lacuna e não pode ser aprovada.
- Teste real controlado (envio para o 49 92000-4388) com a sua autorização. O ambiente já está preparado para isso desde a V2.5.
- Item 19 (WhatsApp Business no celular continua funcionando): conferir no aparelho depois do teste real.
