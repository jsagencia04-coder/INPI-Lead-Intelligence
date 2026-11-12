# V2.4 — Foco comercial: manifestação à oposição e recurso contra indeferimento

Estado em 12/11/2026. Uma migration incremental: `20261115000015_pipelines_servicos.sql`. Nada foi apagado e nenhum disparo foi feito.

## 1. O que mudou na lógica

| Antes (V2.3) | Agora (V2.4) |
|---|---|
| IPAS009 "Publicado para oposição" (B) gerava leads | Deixa de gerar leads novos. Os leads antigos ficam como histórico. É reversível na tela Despachos. |
| Oposição só entrava como categoria; o prazo era "data + 60" | Pipeline 1 · Manifestação à oposição: o lead é o **titular do pedido** (quem sofreu a oposição) |
| Indeferimento sem verificação do histórico | Pipeline 2 · Recurso contra indeferimento (IPAS024, IPAS658, IPAS774) e deferimento parcial (IPAS781 e IPAS029 com itens excluídos ou indeferidos) |
| Quente = categoria + recência + contato | Quente exige tudo: prazo aberto, nenhuma manifestação/recurso no pePI, contato validado e nenhuma abordagem anterior |

**Quem se opôs nunca vira lead.** A RPI não informa o opositor no despacho IPAS423; ela traz só o protocolo e a data da oposição. O nome do opositor vem das petições do pePI (serviço 332/3022) e aparece só como informação complementar, com a fonte.

### Fatos usados, todos com fonte

- **RPI:**
  - data da publicação;
  - protocolo e data da oposição (texto do IPAS423);
  - despachos posteriores do mesmo processo:
    - IPAS360 = recurso interposto;
    - IPAS235/237 = recurso julgado;
    - deferimento, indeferimento, concessão ou arquivamento depois da oposição;
    - desistência total.
- **pePI**, petições do processo (protocolo, data, serviço e cliente):
  - 339 = Manifestação;
  - 3000/30001 = Recurso contra indeferimento;
  - 332/3022 = Oposição.

  Ficam guardadas na tabela `process_peticoes`, com histórico.

### Prazos

Os dois prazos são de 60 dias:

- manifestação: LPI art. 158 §1º;
- recurso: LPI art. 212.

Regras da contagem:

- a contagem começa no 1º dia útil após a publicação na RPI;
- se o vencimento cair em dia sem expediente, ele é prorrogado para o 1º dia útil seguinte (LPI arts. 221, 224 e 226 e a orientação "Prazos" do próprio pePI);
- a tabela `feriados` traz os feriados nacionais de 2025 a 2028;
- pontos facultativos (Carnaval, Corpus Christi) entram desligados, o que mantém a contagem conservadora.

Indicadores de prazo:

| Indicador | Significado |
|---|---|
| em andamento | prazo aberto |
| próximo do encerramento | 15 dias ou menos |
| encerrado | prazo vencido |
| validar | sem data de publicação |
| necessita validação jurídica | deferimento parcial ou anulação de despacho |

A data final e a fonte do cálculo aparecem em todas as telas e na exportação.

### Classificação de cada oportunidade

| Classe | Quando |
|---|---|
| QUENTE | Prazo aberto, nenhuma petição de manifestação/recurso no pePI após a publicação, contato validado e nenhuma abordagem |
| MORNO | Prazo aberto, mas falta algo (petições ainda não conferidas, contato não validado, já abordado ou validação jurídica). Os motivos ficam listados. |
| PENDENTE | Sem contato encontrado ou sem data para calcular o prazo |
| HISTÓRICO | Prazo encerrado, medida já protocolada ou decisão posterior |

Cada lead (um por titular) tem uma classificação por pipeline (`classificacao_oposicao` e `classificacao_recurso`) e um serviço principal.

## 2. Operação semanal e histórico

1. Na terça, o sistema detecta a RPI e extrai a seção de marcas (oposições, indeferimentos e deferimentos parciais).
2. Cruza com os processos já acompanhados: tudo o que for publicado deles é gravado.
3. A Análise Processual consulta as petições no pePI, primeiro SC, depois RS, PR e os demais estados.
4. A Pesquisa Comercial busca os contatos e a Qualificação classifica cada oportunidade.

A migration busca automaticamente as **9 edições anteriores (~60 dias)**, que ainda podem ter prazo aberto.

- Quando uma edição antiga é importada depois da mais recente, a mais recente é relida para capturar o que veio depois (recurso, decisão).
- Uma edição antiga nunca sobrescreve o titular atual do processo.
- A agenda `prazos-servicos` (a cada 6 h) recalcula os prazos.

## 3. Telas

- **Oportunidades de serviço** (`/oportunidades`, novo):
  - as duas frentes em abas, com indicadores separados;
  - filtros: estado, cidade, RPI, data, situação, prazo, prioridade e contato, além da busca;
  - lista ordenada SC → RS → PR com prazo, medida, opositor e contatos, com link para o CRM;
  - exportação Excel/CSV.
- **Painel executivo:** bloco "Frentes comerciais" (manifestação × recurso) com o consolidado da diretoria e as melhores oportunidades.
- **SILVANE (Central de Operações):** resumo executivo das duas frentes.
- **Mapa:**
  - métricas novas: sofreram oposição, manifestações cabíveis, indeferidas, recursos cabíveis e quentes;
  - filtro de prazo;
  - no painel do estado: sofreram oposição, cabíveis e já protocoladas; indeferidas, cabíveis e já protocolados; contatos; quentes.
- **Leads:** filtro e coluna "Serviço" e filtro de classificação. No detalhe do lead, a seção "Serviço a oferecer" mostra prazo, medida, opositor, fundamentação, motivos e fontes, além das petições do pePI.
- **Alertas:** prazos perto do fim e oportunidades quentes.

## 4. Agentes (sem agentes novos)

| Agente | Responsabilidade |
|---|---|
| Rafael | Monitoramento e busca do histórico da RPI |
| Otávio | Extração INPI: oposições apresentadas, indeferimentos e deferimentos parciais |
| Vítor | Análise Processual: titular correto, petições no pePI, manifestação ou recurso já protocolados, opositor, prazos |
| Sérgio | Pesquisa Comercial do titular |
| Quintino | Qualificação por frente |
| SILVANE | Supervisão e resumo executivo |

## 5. Testes com processos reais (RPI 2904, 2905, 2909, 2914 e pePI consultados em 12/11/2026)

`backend/tests/test_servicos_reais.py`. Nomes de pessoas físicas foram substituídos nos arquivos de teste.

| Caso | Processo real | Resultado |
|---|---|---|
| Marca que sofreu oposição | 944040470 TELEVAULT (CEI Controles, SC) | Manifestação; prazo 11/01/2027; opositor ASSA ABLOY (pePI); QUENTE com contato validado |
| Quem apresentou oposição | ASSA ABLOY, EPIROC, INP, GLOBO | Nenhum vira titular ou lead |
| "Publicado para oposição" | 945199783 (IPAS009) | Nenhuma oportunidade de serviço |
| Já recebeu manifestação | 943447259 HEALTH ESSENCE (SC) | Petição 339 de 23/09/2026 encontrada → HISTÓRICO |
| Oposição com prazo encerrado | 942100506 Instituto Ela por Elas (DF) | Vencimento 03/11/2026 (Finados prorroga) → HISTÓRICO |
| Indeferida sem recurso | 938028383 ESCOLA DAS CIDADES (SC) | Recurso; prazo 11/01/2027; nenhum recurso no pePI → QUENTE |
| Indeferida com recurso | 930932480 EKOA LIFE SCIENCES (DF) | IPAS360 na RPI 2914 (protocolo 850260549596) → HISTÓRICO |
| Deferimento parcial | 939053594 XUCRO CORAÇÃO (SC); 501881667 (IPAS781) | Pipeline 2 separado, validação jurídica, no máximo MORNO; Madri não elegível |
| Dados incompletos | 944032028 EPROK (IPAS423 sem marca/classe, sem contato) | PENDENTE, nada inventado |
| Pessoa física | 943447259, 930647033 | Lead criado; tipo "indefinido" até o CNPJ (regra existente) |
| Pessoa jurídica | 944040470, 938028383 | PJ |
| Mesmo titular em edições diferentes | NANOVETORES 938471708 (RPI 2905) e 943766842 (RPI 2909) | 1 lead e 2 oportunidades: recurso HISTÓRICO e manifestação aberta até 07/12/2026 |
| Reimportação | 2914 e 2904 de novo | Nada duplica; titular preservado |

Resultado geral:

- **Backend:** 161 testes aprovados (5 novos com dados reais).
- **Frontend:** 34 testes aprovados.
- ruff, tsc e eslint limpos; build concluído.

## 6. Pendências e observações

- Sem a base da Receita, o município não aparece e a UF fica "estimada".
- A medida só é "não identificada" depois da consulta ao pePI. Até lá, a oportunidade fica MORNA ("petições ainda não conferidas"), de propósito.
- Processos com procurador continuam descartados (regra original do projeto: titular sem procurador).
- A mensagem de WhatsApp sugerida ainda é genérica. Se quiser, criamos modelos específicos para manifestação e para recurso, sempre com aprovação humana.
