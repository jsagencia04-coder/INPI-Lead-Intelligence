# V2.3 — Mapa Comercial do Brasil, Monitoramento Automático da RPI e Priorização de Leads

Estado em 12/11/2026. Nada foi apagado, nada publicado, nenhum disparo feito. Uma migration incremental: `20261114000014_mapa_rpi_semanal.sql`.

## 1. O que foi implementado

| Item | Onde |
|---|---|
| Mapa interativo dos 26 estados + DF, cores por volume ou % do estado, filtros (edição, período, situação A/B, temperatura), painel do estado ao clicar | `/mapa` · `GET /api/mapa`, `GET /api/mapa/{uf}` |
| Categoria A "Oposição apresentada" (IPAS423) × B "Publicado para oposição" (IPAS009), com data do protocolo da oposição | migration 0014 · `leads.py` |
| Localização do titular: **confirmada** (Receita/CNPJ) > **estimada** (UF declarada na RPI) > **pendente**; correção manual pelo revisor | `geo_atualizar()` · `POST /api/holders/{id}/localizacao` |
| Monitoramento automático toda terça (fuso America/Sao_Paulo), repetido a cada 10 min das 05h às 23h59; quarta como contingência para feriado/atraso; sem duplicidade (dedupe por edição) | agenda `rpi-terca` · `scheduler.py` |
| Operação semanal orquestrada pela SILVANE: RPI detectada → dados extraídos → SC → RS → PR → demais | jobs `rpi.semana` e `rpi.semana_check` · `/rpi-semanal` |
| Prioridade territorial SC > RS > PR > demais (ordem dos demais configurável pelo admin) | `uf_prioridade` · `GET/PUT /api/uf-prioridade` |
| Temperatura quente / morno / em pesquisa, com os motivos | `leads.temperatura`, `temperatura_motivos` |
| Alertas: falha na RPI, RPI atrasada (terça 14h sem edição), primeiros leads quentes de SC, localização pendente | `overview.py` (sino e menu) |
| Lista de leads por estado integrada ao CRM, exportação CSV/Excel com temperatura e localização | `/mapa`, `/leads` |
| Histórico semanal, comparativo por edição e relatório executivo por estado (SC por padrão) | `/rpi-semanal`, painel da SILVANE no escritório, card no Painel executivo |
| Responsabilidades dos agentes | SILVANE (supervisão), Rafael (monitoramento INPI), Otávio (análise processual), Carla (geografia e CNPJ), Sérgio (pesquisa), Valéria (validação), Quintino (qualificação) |

Edição ainda não processada aparece como **"sem dados"** (hachurado), nunca como zero.

## 2. Regras de temperatura

- **Em pesquisa**: um destes casos:
  - nenhum contato encontrado;
  - localização pendente;
  - CNPJ ambíguo sem contato validado.
- **Quente**: precisa de tudo isto:
  - oposição apresentada (A) ou publicação há até 30 dias;
  - contato comercial validado;
  - nenhuma abordagem anterior.
- **Morno**: os demais casos.

Oposição sozinha não torna o lead validado.

Os motivos aparecem na tabela (tooltip) e na exportação.

## 3. Testes (12/11/2026)

| Verificação | Resultado |
|---|---|
| Backend pytest | 156 aprovados (15 novos em `test_mapa_rpi_semanal.py`) |
| Frontend vitest | 32 aprovados |
| ruff, tsc, eslint | sem apontamentos |
| next build | concluído |
| Telas conferidas no navegador (desktop e celular) com dados fictícios | ok |

Fluxos cobertos pelos testes novos:
- janela de terça no fuso de SP;
- detecção automática da edição;
- A × B com data do protocolo;
- localização confirmada, estimada, pendente e manual;
- mapa sem dados;
- fila com SC primeiro;
- ordem configurável;
- reprocessamento sem duplicar;
- regras de temperatura;
- marco e alerta dos quentes de SC, relatório e exportação;
- etapas da Central RPI;
- alertas de atraso e falha;
- arquivo corrompido;
- permissões por perfil.

## 4. Ao publicar

- A migration 0014 roda sozinha no início da API.
  - Ela reprocessa a última edição já processada para capturar as oposições apresentadas (IPAS423), que antes não eram gravadas.
  - É idempotente e não duplica dados.
  - Ela só reclassifica o IPAS423 se a configuração dele não tiver sido alterada por você.
- Sem a base da Receita (agenda `cnpj-receita` desligada), a localização fica "estimada" pela UF da RPI. Para "confirmada", ligue a agenda (cerca de 8 GB).
- Para desligar o fluxo semanal automático, use `RPI_OPERACAO_SEMANAL_AUTO=false`.

## 5. Pendências

- Município só aparece com a base da Receita ligada. A RPI não informa município.
- Do escopo V2.0 ainda faltam:
  - campanha de primeiro contato;
  - Sales Closer;
  - credenciais da Meta para o número +55 49 3191-3301.
