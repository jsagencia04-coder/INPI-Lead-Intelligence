# WhatsApp Business Platform (Cloud API oficial)

O sistema usa **somente a API oficial da Meta**. Não há automação do WhatsApp Web.
Sem credenciais, ou com `WHATSAPP_ENVIO_ATIVO=false`, tudo funciona em **simulação**: nada sai do sistema.

## 1. O que você precisa criar na Meta (só você pode fazer)

1. **Conta Meta Business** (business.facebook.com) com os dados do seu negócio. A verificação do negócio pode ser exigida para sair dos limites iniciais.
2. **App** em developers.facebook.com, tipo "Business", com o produto **WhatsApp** adicionado.
3. **Número de telefone dedicado**. Ele não pode estar em uso no aplicativo WhatsApp comum ou Business do celular. Para os primeiros testes a Meta oferece um número de teste, que só envia para destinatários que você cadastrar.
4. **Token permanente**: crie um *usuário do sistema* nas configurações do negócio e gere um token com as permissões `whatsapp_business_messaging` e `whatsapp_business_management`. O token temporário da tela inicial expira em cerca de 24 horas.
5. **Template de mensagem** aprovado (seção 3).
6. **Webhook** (seção 4).

Os nomes exatos de telas mudam; siga a documentação oficial: https://developers.facebook.com/docs/whatsapp/cloud-api

## 2. Variáveis (arquivo `backend/.env`)

| Variável | Onde encontrar |
|---|---|
| `WHATSAPP_PHONE_NUMBER_ID` | Painel do app → WhatsApp → API Setup ("Phone number ID") |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | Mesma tela ("WhatsApp Business Account ID") |
| `WHATSAPP_ACCESS_TOKEN` | Token do usuário do sistema |
| `WHATSAPP_APP_SECRET` | Painel do app → Configurações → Básico ("App secret"). Sem ele o sistema **recusa** webhooks |
| `WHATSAPP_VERIFY_TOKEN` | Você inventa (texto longo e aleatório) e repete no cadastro do webhook |
| `WHATSAPP_TEMPLATE_NAME` | Nome do template aprovado |
| `WHATSAPP_TEMPLATE_LANGUAGE` | `pt_BR` |
| `WHATSAPP_ENVIO_ATIVO` | `false` = simulação. `true` só na homologação/produção |
| `WHATSAPP_NUMEROS_TESTE` | Seus próprios números, ex.: `+5511999998888,+5511988887777` |
| `WHATSAPP_LIMITE_POR_MINUTO` / `_POR_DIA` | Padrão 10 e 50 |

Nunca coloque essas chaves no frontend, em prints ou em conversas. O sistema só mostra se cada uma está definida.

## 3. Template

O sistema envia **5 variáveis**, todas fatos oficiais do processo:
`{{1}}` marca · `{{2}}` nº do processo · `{{3}}` despacho · `{{4}}` nº da RPI · `{{5}}` data da RPI.

Sugestão de texto (ajuste o nome; não inclua prazos nem afirmações sobre perda de direitos):

> Olá. Sou [seu nome], agente de propriedade industrial. Na Revista da Propriedade Industrial nº {{4}}, de {{5}}, publicada pelo INPI, consta o despacho "{{3}}" no processo {{2}}, da marca {{1}}. Posso explicar o que essa publicação significa? Para não receber mais mensagens, responda SAIR.

A Meta classifica esse tipo de mensagem como **marketing** e exige que o destinatário tenha optado por recebê-la.

## 4. Webhook

Endereço: `https://SEU-DOMINIO/webhooks/whatsapp` — campos assinados: `messages`.

A Meta só chama endereços **públicos com HTTPS**. O sistema rodando em `localhost` não recebe webhooks: é preciso publicá-lo (por exemplo com o `render.yaml` do projeto) ou usar um túnel HTTPS durante a homologação. Sem webhook, as mensagens param em "aceita pela Meta" e o sistema **não presume** entrega nem leitura.

Segurança do webhook: verificação por token (GET), assinatura HMAC-SHA256 de cada aviso (`X-Hub-Signature-256`), limite de tamanho e descarte de eventos repetidos.

## 5. Como o envio funciona

1. Uma pessoa prepara **uma** mensagem para **um** contato de um lead aprovado.
2. A mensagem recebe uma chave única por contato + processo + template: pedir de novo não cria outra.
3. O agente `whatsapp.send` confere, nesta ordem: envio ligado, integração configurada, login obrigatório ativo, opt-out, contato válido, número na lista de homologação, template aprovado na Meta, limites por minuto e por dia.
4. Qualquer falha na conferência = mensagem **bloqueada**, com o motivo.
5. Resposta da Meta: `aceita`. Depois, só o webhook muda para `enviada`, `entregue`, `lida` ou `falhou`.

**Retry seguro:** só repete quando o pedido comprovadamente não chegou à Meta (sem conexão, limite de taxa). Timeout ou erro 5xx é resultado incerto: fica como `falhou` e não é reenviado sozinho.

**Opt-out imediato:** resposta `SAIR`, `PARAR`, `PARE`, `STOP`, `CANCELAR`, `DESCADASTRAR` ou equivalente bloqueia o número, registra data e origem, revoga consentimentos e cancela mensagens na fila.

## 6. Limitações atuais (de propósito)

- Envio real **só para os números de `WHATSAPP_NUMEROS_TESTE`**, até a regra de consentimento ser implantada.
- Envio real **exige `AUTH_MODE=supabase`** (login obrigatório). No modo sem login, tudo é bloqueado.
- Não há campanha nem envio em lote.
- Respostas são gravadas, mas ainda não classificadas.
