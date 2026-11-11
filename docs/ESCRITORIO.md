# INPI AI Office: escritório virtual dos agentes

**Visual (v1.5):** cobertura corporativa à noite.
- **Ambiente:** fachada de vidro com a cidade iluminada, laje de pedra e a marca INPI AI OFFICE em latão.
- **Salas:** piso de madeira em tábuas, tapetes nos tons de cada departamento, divisórias de vidro com caixilhos e placas de latão.
- **Mobiliário:** mesas de nogueira com pés metálicos, monitores duplos, luminárias pendentes com foco de luz, plantas altas, sofá de design e mesa de reunião de vidro.
- **Acabamento:** personagens com contorno e sombreado, e moldura da tela em tema escuro.

Desempenho medido: 60 quadros por segundo, cerca de 2.300 elementos SVG, sem filtros pesados.

Tela: **/escritorio** (menu "Escritório (AI Office)").

## Status por etapa

| Etapa | Situação |
|---|---|
| 1. Estrutura visual do escritório | **Pronta** |
| 2. Departamentos e personagens | **Pronta** |
| 3. Painel lateral e painel de atividades | **Parcial:** indicadores reais no topo e feed de atividades em tempo real |
| 4. Interação com agentes e tarefas | **Parcial:** histórico real e resultado da última execução no cartão do agente |
| 5. Eventos do backend (WebSocket) | **Pronta** |
| 6. Conexão com os agentes reais | **Pronta** |
| 7. Testes de tempo real | **Pronta** (testes automáticos + teste ao vivo) |

A tela abre em **Dados reais**. A **Demonstração** continua disponível no seletor e
sempre aparece com a faixa amarela.

## Como o estado real é calculado (nada é simulado)

| Estado | Regra (tabela `jobs`) |
|---|---|
| WORKING | há um job do agente em execução |
| THINKING | idem, para agentes que chamam a IA (`research.holder`, `sales.summarize_batch`) |
| ERROR | falha definitiva nos últimos 15 min |
| WAITING | há jobs do agente prontos na fila |
| COMPLETED | concluiu algo nos últimos 2 min |
| IDLE | nenhum dos casos acima |

A coordenadora (Clara) reflete o agendador. Ela fica em ERROR quando algum agendamento
ativo está atrasado há mais de 10 minutos, o que indica worker parado.

## Eventos

Os eventos são gravados por **triggers no banco** (migration `20261111000005_eventos_escritorio.sql`).
Assim, qualquer worker, em qualquer máquina, gera eventos sem mudar o código dos agentes.

| Grupo | Eventos |
|---|---|
| Jobs | `task.created`, `task.started`, `task.completed`, `task.failed` |
| Agentes | `agent.started`, `agent.thinking`, `agent.waiting`, `agent.completed`, `agent.error` |
| Negócio | `rpi.imported`, `rpi.processed`, `lead.discovered`, `lead.qualified`, `lead.validated` |

Cada evento traz data, agente, tipo, descrição, resultado e referência (`job:`, `rpi:`,
`lead:`, `processo:`, `titular:`). A retenção é de 30 dias, com limpeza no relatório diário.

## Tempo real

- `GET /api/office/state`: estado por tipo de job, indicadores e saúde do sistema.
- `GET /api/office/events?after=ID`: eventos novos.
- `GET /api/office/history?tipos=...`: últimas execuções de um personagem.
- `WS /ws/office`: snapshot ao conectar e atualização a cada evento, via `LISTEN/NOTIFY`
  do Postgres. Um sinal de vida a cada 5 s. Em produção, exige o token do Supabase.
- **Reconexão:** se o WebSocket cair, a tela reconecta com espera de 1, 2, 5, 10 e 30 s
  e, enquanto isso, consulta a API a cada 3 s. A faixa do topo mostra o modo atual.

## Arquivos das Etapas 5 e 6

- `supabase/migrations/20261111000005_eventos_escritorio.sql`: tabela `agent_events` e triggers.
- `backend/app/api/office_routes.py`: estado, eventos, histórico e WebSocket.
- `backend/tests/test_office.py`: 7 testes (triggers, estados, agendador, WebSocket, login).
- `frontend/src/office/real.ts`: conversão do estado real para a cena (testada).
- `frontend/src/office/use-real.ts`: WebSocket, reconexão e consulta de reserva.
- `frontend/src/app/escritorio/page.tsx`: modos real e demonstração, indicadores, feed e histórico.

## Arquivos criados

| Arquivo | O que faz |
|---|---|
| `frontend/src/app/escritorio/page.tsx` | Página: cabeçalho, faixa de demonstração, atalhos de departamento, legenda e cartão de detalhes |
| `frontend/src/office/types.ts` | Tipos: estados (`idle`, `working`, `thinking`, `waiting`, `completed`, `error`), agente, departamento |
| `frontend/src/office/config.ts` | Os 8 departamentos e os 13 personagens, cada um ligado aos tipos de job reais do backend |
| `frontend/src/office/iso.ts` | Projeção isométrica 2:1, caixas isométricas, zoom ancorado no cursor |
| `frontend/src/office/demo.ts` | Fonte de **demonstração** determinística e cálculo do estado do departamento |
| `frontend/src/office/use-demo.ts` | Hook que avança a demonstração (pausa com a aba escondida). Na Etapa 5, a fonte real o substitui |
| `frontend/src/office/office.css` | Animações por estado (só `transform` e `opacity`); respeita "reduzir movimento" |
| `frontend/src/office/components/office-scene.tsx` | Cena SVG: zoom (roda, pinça, botões, teclado `+` `-` `0`), arraste e setas |
| `frontend/src/office/components/room.tsx` | Sala: piso, paredes, placa com lâmpada de estado e ordenação por profundidade |
| `frontend/src/office/components/furniture.tsx` | Mesas com tela que acende, plantas, servidores, armários, estantes, quadros e outros objetos |
| `frontend/src/office/components/agent-sprite.tsx` | Personagem em pixel art (desenho original), cores por agente, ícones de estado |
| `frontend/src/office/office.test.ts` | 16 testes de unidade (`npm test`) |

## Arquivos alterados

- `frontend/src/components/sidebar.tsx`: item novo no menu e menu recolhível no celular (vale para todas as telas).
- `frontend/src/app/layout.tsx`: espaço para a barra superior no celular.
- `frontend/package.json`: `vitest` e o script `npm test`.
- `.github/workflows/ci.yml`: roda `npm test`.

O backend, o banco e as migrations não foram alterados nesta entrega.

## Personagens e agentes reais

| Personagem | Departamento | Agente real (tipo de job) | Modelo |
|---|---|---|---|
| Clara | Diretoria | agendador, `system.ping` | sem IA |
| Rafael | RPI | `rpi.discover` | sem IA |
| Paula | RPI | `rpi.collect` | sem IA |
| Otávio | Processamento | `rpi.parse` | sem IA |
| Inês | INPI | `inpi.verify_pending` | sem IA |
| Vítor | INPI | `inpi.verify` | sem IA |
| Carla | Investigação | `cnpj.sync` | sem IA |
| Sérgio | Investigação | `research.free`, `research.free_batch` | sem IA |
| Íris | Investigação | `research.holder`, `research.batch` | claude-sonnet-5-5 |
| Valéria | Validação | `lead.validate_contacts` | sem IA |
| Quintino | Comercial | `leads.build` | sem IA |
| Renata | Comercial | `sales.summarize_batch` | claude-haiku-5-5 |
| Rui | Relatórios | `reports.weekly` | sem IA |

## Verificação feita

- **Testes de unidade:** 11 de 11 passaram. O lint e a checagem de tipos não acusaram erros.
- **Build de produção:** a página do escritório tem 14 kB.
- **Desempenho (desktop 1440×900, 4 s de animação):** 60 quadros por segundo, pior quadro de 17 ms, 28 ms de script, cerca de 1.300 elementos SVG e 6 MB de memória JS.
- **Responsividade:** conferida no desktop, no iPad e no iPhone 13. No celular, o cartão de detalhes aparece como uma folha inferior e o menu recolhe.
