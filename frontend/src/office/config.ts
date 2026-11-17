import type { Agent, Department } from "./types";

/** Dimensões das salas e corredores (em tiles). */
export const ROOM_W = 8;
export const ROOM_D = 7;
export const GAP = 2;
export const WALL_H = 58;

export function roomOrigin(d: Pick<Department, "col" | "row">) {
  return { x: d.col * (ROOM_W + GAP), y: d.row * (ROOM_D + GAP) };
}

export const DEPARTAMENTOS: Department[] = [
  { id: "diretoria", nome: "Diretoria", cor: "#5b3a8c", col: 0, row: 0,
    descricao: "Sala da SILVANE, diretora de operações: agenda as execuções, distribui o trabalho e acompanha a fila.",
    props: [{ kind: "sofa", x: 5.4, y: 4.6 }, { kind: "plant", x: 0.3, y: 0.3 }, { kind: "shelf", x: 0.2, y: 3 },
      { kind: "plant", x: 7.2, y: 0.3 }] },
  { id: "rpi", nome: "RPI", cor: "#1f4e8c", col: 1, row: 0,
    descricao: "Acompanha as edições semanais da Revista da Propriedade Industrial e baixa os arquivos oficiais.",
    props: [{ kind: "boxes", x: 6.4, y: 0.3 }, { kind: "printer", x: 0.3, y: 4.8 }, { kind: "plant", x: 7.2, y: 5.8 }] },
  { id: "processamento", nome: "Processamento", cor: "#136f7a", col: 2, row: 0,
    descricao: "Interpreta o XML da RPI e extrai processos, titulares, despachos e procuradores.",
    props: [{ kind: "server", x: 6.6, y: 0.3 }, { kind: "server", x: 6.6, y: 1.5 }, { kind: "plant", x: 0.3, y: 5.8 }] },
  { id: "inpi", nome: "INPI", cor: "#1f6b4f", col: 3, row: 0,
    descricao: "Consulta cada processo na base do INPI e confirma marca, situação e procurador.",
    props: [{ kind: "cabinet", x: 0.2, y: 0.4 }, { kind: "cabinet", x: 0.2, y: 1.4 }, { kind: "water", x: 7.2, y: 5.6 }] },
  { id: "investigacao", nome: "Investigação", cor: "#a8742a", col: 0, row: 1,
    descricao: "Pesquisa os titulares: base CNPJ da Receita, sites oficiais e, se ligado, a pesquisa web com IA.",
    props: [{ kind: "board", x: 0.2, y: 2.6 }, { kind: "plant", x: 7.2, y: 0.3 }, { kind: "boxes", x: 0.4, y: 5.8 }] },
  { id: "validacao", nome: "Validação", cor: "#9b2c3a", col: 1, row: 1,
    descricao: "Confere telefones, e-mails e sites: formato, página de origem e vínculo com o titular.",
    props: [{ kind: "cabinet", x: 7, y: 0.4 }, { kind: "plant", x: 0.3, y: 0.3 }, { kind: "printer", x: 0.3, y: 5.6 }] },
  { id: "comercial", nome: "Comercial", cor: "#a03d68", col: 2, row: 1,
    descricao: "Monta e pontua os leads, prepara as abordagens e envia o WhatsApp oficial para contatos autorizados.",
    props: [{ kind: "table", x: 4.6, y: 4.4 }, { kind: "plant", x: 7.2, y: 0.3 }, { kind: "water", x: 0.3, y: 5.6 }] },
  { id: "ti", nome: "TI", cor: "#0f766e", col: 4, row: 1,
    descricao: "Sala do JULIO: monitora o sistema 24 horas, de uma Revista à outra (terça a terça), corrige sozinho o que é seguro e alerta quando algo falha.",
    props: [{ kind: "server", x: 6.6, y: 0.3 }, { kind: "server", x: 6.6, y: 1.5 }, { kind: "server", x: 6.6, y: 2.7 },
      { kind: "chart", x: 0.2, y: 2.4 }, { kind: "plant", x: 0.3, y: 5.8 }] },
  { id: "relatorios", nome: "Relatórios", cor: "#4a5568", col: 3, row: 1,
    descricao: "Consolida os resultados da semana e prepara relatórios e exportações.",
    props: [{ kind: "chart", x: 0.2, y: 2.4 }, { kind: "shelf", x: 6.8, y: 0.2 }, { kind: "plant", x: 7.2, y: 5.8 }] },
];

/** Visual corporativo: camisa = cor do blazer (tons sóbrios), destaque = gravata/lenço, longo = cabelo longo. */
const pessoa = (camisa: string, cabelo: string, pele: string, calca = "#2b3240", destaque = "#c9a45c", longo = false) =>
  ({ camisa, cabelo, pele, calca, destaque, longo });

/** Um personagem por agente real do sistema (tipos de job do backend). */
export const AGENTES: Agent[] = [
  { id: "coordenador", nome: "SILVANE", cargo: "Diretora de Operações IA", departamento: "diretoria", lider: true,
    jobTypes: ["scheduler", "system.ping", "rpi.semana", "rpi.semana_check"], modelo: "sem IA", mesa: { x: 2.2, y: 1.6 },
    especialidade: "Supervisiona as duas frentes de receita (manifestação à oposição e recurso de indeferimento): na terça distribui o trabalho por estado (SC, RS, PR e demais), acompanha prazos e resultados e entrega o resumo executivo com as melhores oportunidades.",
    modulo: { href: "/rpi-semanal", rotulo: "Operação semanal" },
    visual: pessoa("#3b2f5c", "#2a1a12", "#d9a27a", "#232634", "#c9a45c", true) },
  { id: "rpi-monitor", nome: "Rafael", cargo: "Monitoramento INPI", departamento: "rpi",
    jobTypes: ["rpi.discover", "rpi.historico"], modelo: "sem IA", mesa: { x: 1.4, y: 1.6 },
    especialidade: "Monitora o INPI (terça e quarta a cada 10 min; demais dias a cada 3 h), dispara a coleta assim que a RPI sai e busca as edições anteriores para cruzar prazos ainda abertos.", modulo: { href: "/rpi", rotulo: "Edições da RPI" }, executar: "rpi.discover",
    visual: pessoa("#1e3a5f", "#1a1a1a", "#c68a5e", "#2b3240", "#3b82f6") },
  { id: "rpi-coletor", nome: "Paula", cargo: "Coletora de arquivos", departamento: "rpi",
    jobTypes: ["rpi.collect"], modelo: "sem IA", mesa: { x: 4.4, y: 1.6 },
    especialidade: "Baixa os arquivos oficiais da revista e guarda os originais com SHA-256.", modulo: { href: "/rpi", rotulo: "Edições da RPI" },
    visual: pessoa("#2c4a6e", "#7a4a1c", "#f1c7a3", "#2b3240", "#93c5fd", true) },
  { id: "parser", nome: "Otávio", cargo: "Extração INPI", departamento: "processamento",
    jobTypes: ["rpi.parse"], modelo: "sem IA", mesa: { x: 2.4, y: 2.4 },
    especialidade: "Lê o XML oficial da RPI e extrai primeiro as oposições apresentadas contra pedidos de marca, os indeferimentos e os deferimentos parciais; cruza com o histórico dos processos.", modulo: { href: "/processos", rotulo: "Processos" },
    visual: pessoa("#24474f", "#2e2018", "#8d5a3b", "#2b3240", "#14b8a6") },
  { id: "inpi-planejador", nome: "Inês", cargo: "Planejadora de consultas", departamento: "inpi",
    jobTypes: ["inpi.verify_pending"], modelo: "sem IA", mesa: { x: 2.4, y: 1.6 },
    especialidade: "Escolhe quais processos consultar no INPI, por prioridade e prazo.", modulo: { href: "/processos", rotulo: "Processos" }, executar: "inpi.verify_pending",
    visual: pessoa("#2f4f43", "#5a2a14", "#e8b48f", "#2b3240", "#34d399", true) },
  { id: "inpi-verificador", nome: "Vítor", cargo: "Análise Processual", departamento: "inpi",
    jobTypes: ["inpi.verify", "servicos.analisar"], modelo: "sem IA", mesa: { x: 4.8, y: 3.4 },
    especialidade: "Confirma quem SOFREU a oposição (o titular), consulta as petições no pePI, identifica manifestação ou recurso já protocolado, quem se opôs e calcula os prazos com a fonte.", modulo: { href: "/processos?procurador_status=sem_confirmado", rotulo: "Processos confirmados" },
    visual: pessoa("#26392f", "#1f2937", "#c68a5e", "#2b3240", "#10b981") },
  { id: "cnpj", nome: "Carla", cargo: "Inteligência Geográfica e CNPJ", departamento: "investigacao",
    jobTypes: ["cnpj.sync", "cnpj.recontatos"], modelo: "sem IA", mesa: { x: 2.4, y: 1.4 },
    especialidade: "Confirma CNPJ e endereço na Receita, separa homônimos e define a UF do titular: confirmada, estimada ou pendente.", modulo: { href: "/contatos", rotulo: "Central de contatos" }, executar: "cnpj.recontatos",
    visual: pessoa("#5a4632", "#1a1a1a", "#f1c7a3", "#2b3240", "#f59e0b", true) },
  { id: "sites", nome: "Sérgio", cargo: "Pesquisa Comercial", departamento: "investigacao",
    jobTypes: ["research.free", "research.free_batch"], modelo: "sem IA", mesa: { x: 5.2, y: 1.4 },
    especialidade: "Pesquisa o titular da marca (empresa ou pessoa responsável pelo pedido) e encontra WhatsApp comercial, telefone, e-mail corporativo e site oficial, sempre com fonte.", modulo: { href: "/contatos?filtro=whatsapp", rotulo: "WhatsApp encontrados" }, executar: "research.free_batch",
    visual: pessoa("#4b3a2a", "#5c3a1a", "#8d5a3b", "#2b3240", "#d97706") },
  { id: "pesquisa-ia", nome: "Íris", cargo: "Pesquisadora web (IA)", departamento: "investigacao",
    jobTypes: ["research.holder", "research.batch"], modelo: "claude-sonnet-5-5", mesa: { x: 3.8, y: 4.2 },
    especialidade: "Pesquisa web com IA para titulares sem WhatsApp, com evidência citada e orçamento semanal.", modulo: { href: "/operacao", rotulo: "Custos de IA" },
    visual: pessoa("#4a3b2a", "#3b1f4f", "#e8b48f", "#2b3240", "#a78bfa", true) },
  { id: "validador", nome: "Valéria", cargo: "Validação Comercial", departamento: "validacao",
    jobTypes: ["lead.validate_contacts"], modelo: "sem IA", mesa: { x: 2.8, y: 2.2 },
    especialidade: "Reconfere cada contato na página de origem, valida formato e domínio, e separa candidato de validado.", modulo: { href: "/contatos?filtro=pendentes", rotulo: "Contatos pendentes" },
    visual: pessoa("#5a2a30", "#1c1917", "#c68a5e", "#2b3240", "#f87171", true) },
  { id: "qualificador", nome: "Quintino", cargo: "Qualificação de Leads", departamento: "comercial",
    jobTypes: ["leads.build"], modelo: "sem IA", mesa: { x: 1.4, y: 1.4 },
    especialidade: "Classifica cada oportunidade por frente (manifestação × recurso) em quente, morno, histórico ou pendente: confere prazo, petições, contato e abordagem anterior, com os motivos.", modulo: { href: "/pipeline", rotulo: "Pipeline comercial" }, executar: "leads.build",
    visual: pessoa("#4d2a3e", "#3f2a1d", "#f1c7a3", "#2b3240", "#f472b6") },
  { id: "redator", nome: "Renata", cargo: "Redatora de abordagens", departamento: "comercial",
    jobTypes: ["sales.summarize_batch"], modelo: "claude-haiku-5-5", mesa: { x: 4.4, y: 1.4 },
    especialidade: "Escreve o resumo comercial e a sugestão de abordagem de cada lead, só com fatos do processo.", modulo: { href: "/leads", rotulo: "Leads" },
    visual: pessoa("#55304a", "#8a5a2b", "#8d5a3b", "#2b3240", "#c084fc", true) },
  { id: "mensageiro", nome: "Wagner", cargo: "Mensageiro WhatsApp oficial", departamento: "comercial",
    jobTypes: ["whatsapp.send"], modelo: "sem IA", mesa: { x: 0.6, y: 3.6 },
    especialidade: "Envia pela API oficial da Meta só para contatos elegíveis e acompanha entrega, leitura e respostas.",
    modulo: { href: "/whatsapp", rotulo: "WhatsApp Business" },
    visual: pessoa("#1f4440", "#1f2937", "#c68a5e", "#2b3240", "#25d366") },
  { id: "relator", nome: "Rui", cargo: "Analista de relatórios", departamento: "relatorios",
    jobTypes: ["reports.weekly"], modelo: "sem IA", mesa: { x: 3.4, y: 2.2 },
    especialidade: "Consolida a semana: edições, oportunidades, leads, contatos e custos.", modulo: { href: "/relatorios", rotulo: "Relatórios" }, executar: "reports.weekly",
    visual: pessoa("#3a3f4a", "#9ca3af", "#e8b48f", "#2b3240", "#94a3b8") },
  { id: "ti", nome: "JULIO", cargo: "TI · Monitoramento 24 h", departamento: "ti",
    jobTypes: ["sistema.saude"], modelo: "sem IA", mesa: { x: 2.4, y: 2.2 },
    especialidade: "Verifica o sistema a cada 5 minutos, de terça a terça: banco, worker e agendador, fila, tarefas travadas, falhas, WhatsApp, Revista da semana, última importação e disco. Devolve à fila tarefas travadas por queda do worker e alerta no painel quando algo falha.",
    modulo: { href: "/operacao", rotulo: "Saúde do sistema" }, executar: "sistema.saude",
    visual: pessoa("#1f2a37", "#1a1a1a", "#d9a27a", "#232634", "#14b8a6") },
];

export const ESTADOS: Record<string, { rotulo: string; cor: string; descricao: string }> = {
  idle: { rotulo: "IDLE", cor: "#94a3b8", descricao: "Aguardando" },
  working: { rotulo: "WORKING", cor: "#22c55e", descricao: "Executando tarefa" },
  thinking: { rotulo: "THINKING", cor: "#3b82f6", descricao: "Processando informação" },
  waiting: { rotulo: "WAITING", cor: "#f59e0b", descricao: "Aguardando outro agente" },
  completed: { rotulo: "COMPLETED", cor: "#10b981", descricao: "Tarefa concluída" },
  error: { rotulo: "ERROR", cor: "#ef4444", descricao: "Ocorreu uma falha" },
};
