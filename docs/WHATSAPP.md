# WhatsApp comercial (canal do primeiro contato)

## Por que não há uma "verificação automática" de conta

Não existe forma oficial e gratuita de um sistema perguntar ao WhatsApp se um número
tem conta. Os serviços que fazem isso usam métodos não oficiais, que violam os termos
do WhatsApp e podem levar ao bloqueio do seu número. Por isso, a validação é feita por
**evidência** e por **confirmação humana**.

## Níveis

| Nível | Regra | Onde aparece |
|---|---|---|
| **Confirmado** | Você abriu a conversa e confirmou (botão "Confirmar WhatsApp") | `verificado_humano` |
| **Validado pela empresa** | A empresa publica o número como WhatsApp (link `wa.me`/`api.whatsapp.com` ou a palavra "WhatsApp" logo antes do número) numa página com vínculo comprovado (CNPJ, razão social ou nome fantasia), e o número foi reencontrado na revalidação | `dominio_ok` |
| **Candidato** | Celular brasileiro encontrado sem indicação de WhatsApp (site ou Receita) | `formato_ok`, com observação "Candidato" |

Um candidato nunca sobe de nível sozinho: só depois da sua confirmação.

## Score

- WhatsApp validado ou confirmado: +25 pontos.
- Candidato: +8 pontos.

## Na tela do lead

- **Cartão em destaque:** mostra número, nível, fonte, a mensagem pronta (editável) e o campo "Assinar como". O nome fica salvo no seu navegador.
- **Abrir conversa no WhatsApp:** abre o WhatsApp com a mensagem preenchida. O botão só fica liberado depois que o lead é aprovado. O envio é você quem faz.
- **Como foi?** Depois de abrir a conversa, registre o resultado: enviada, respondeu ou número sem WhatsApp. Ele vai para o histórico de prospecção.
- **Só verificar se o número tem WhatsApp:** abre a conversa sem mensagem, para conferir.

## A mensagem

A mensagem usa apenas fatos do processo: RPI, data, marca, número do processo, despacho
e o prazo legal estimado. Termina com a opção de responder SAIR, e o pedido de saída
deve ser registrado com "Opt-out do titular".

## Onde mais aparece

- **Lista de leads:** coluna e filtro (validado / candidato / sem WhatsApp).
- **Exportação:** colunas `whatsapp` e `whatsapp_status`.
- **Indicadores:** "Leads com WhatsApp validado" no dashboard e "WhatsApp validado" no escritório.

## Fontes que buscam WhatsApp

- **Leitor de sites (grátis):** links `wa.me`, `api.whatsapp.com` e números rotulados como WhatsApp.
- **Pesquisa com IA (paga):** o prompt dá prioridade máxima ao WhatsApp e só aceita o tipo `whatsapp` quando a página indica isso.
- **Celulares da Receita e dos sites:** viram candidatos.
