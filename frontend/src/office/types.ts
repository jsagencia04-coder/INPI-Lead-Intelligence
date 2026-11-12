/** Estados operacionais de um agente. Na Etapa 5 passam a vir do backend. */
export type AgentState = "idle" | "working" | "thinking" | "waiting" | "completed" | "error";

export type PropKind =
  | "plant" | "server" | "cabinet" | "shelf" | "board" | "table" | "sofa" | "printer" | "boxes" | "water" | "chart";

export type Department = {
  id: string;
  nome: string;
  descricao: string;
  cor: string; // cor de destaque (placa, faixa da parede)
  col: number; // posição na grade de salas
  row: number;
  props: { kind: PropKind; x: number; y: number }[]; // relativo à sala (tiles)
};

export type Agent = {
  id: string;
  nome: string;
  cargo: string;
  departamento: string;
  /** tipos de job reais que este personagem representa (integração na Etapa 5) */
  jobTypes: string[];
  modelo: string; // "sem IA" para agentes determinísticos
  mesa: { x: number; y: number }; // posição da mesa na sala (tiles)
  visual: { cabelo: string; pele: string; camisa: string; calca: string; destaque: string };
  /** o que o agente sabe fazer melhor (texto da Central de Operações) */
  especialidade?: string;
  /** módulo da plataforma onde o trabalho do agente aparece */
  modulo?: { href: string; rotulo: string };
  /** tarefa que um administrador pode disparar na hora (tipo de job seguro, sem download pesado) */
  executar?: string;
  /** liderança (SILVANE, Diretoria) */
  lider?: boolean;
};

export type AgentStatus = {
  state: AgentState;
  tarefa: string | null;
  desde: number; // epoch ms
  /** origem do dado: na Etapa 1/2 sempre "demo" */
  fonte: "demo" | "real";
};

export type DeptStatus = {
  estado: "Disponível" | "Em atividade" | "Aguardando" | "Atenção";
  tarefas: number;
  ativos: number;
};
