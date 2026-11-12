# V2.2 — Experiência, painéis e Central de Operações IA

## O que mudou
- **Identidade visual:** paleta índigo-violeta, superfícies com profundidade, cores por módulo, tipografia e espaçamento padronizados. Paleta dos gráficos validada para daltonismo (ordem fixa de cores).
- **Navegação:** menu agrupado (Visão geral, Comercial, Inteligência INPI, Operação, Administração) com contadores de pendências; barra superior com caminho da página, busca rápida e notificações.
- **Busca e ações rápidas (Ctrl+K):** abre qualquer módulo, encontra lead por nome ou CNPJ e executa tarefas frequentes.
- **Notificações:** pendências priorizadas (crítico, atenção, oportunidade, para fazer), atualizadas a cada 30 s.
- **Painel executivo:** indicadores com tendência, evolução diária (7/14/30 dias), prioridades de hoje, funil por fase, qualidade dos WhatsApp, despachos, estados, desempenho dos agentes, edições da RPI e todos os indicadores operacionais anteriores.
- **Central de Operações IA:** visão "Equipe" com a Diretoria (SILVANE), fluxo entre setores, cartões de cada agente (função, especialidade, status real, tarefa atual, hoje, fila, falhas, 7 dias, duração média, histórico, módulo e execução sob demanda para administradores). O escritório virtual continua disponível na aba "Escritório virtual".
- **SILVANE:** novo nome visível da agente da Diretoria. Identificador interno (`coordenador`), tipos de job e funcionamento preservados.
- **Novo agente visível:** Wagner, mensageiro do WhatsApp oficial (job `whatsapp.send`); `cnpj.recontatos` passou a aparecer com a Carla.

## Backend (somente leitura, sem migration)
- `GET /api/dashboard/overview?dias=` — indicadores, séries diárias, distribuições, pendências e desempenho por agente.
- `GET /api/alerts` — pendências priorizadas.
- `GET /api/office/stats?dias=` — execuções, sucesso, falhas e duração média por agente.

Nenhuma tabela, regra de negócio ou dado existente foi alterado.
