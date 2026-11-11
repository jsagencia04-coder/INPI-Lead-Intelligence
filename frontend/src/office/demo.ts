/**
 * DADOS DE DEMONSTRAÇÃO — usados enquanto o escritório não está ligado ao backend (Etapas 1 e 2).
 * Nada aqui representa execução real. A tela exibe a faixa "DEMONSTRAÇÃO" sempre que esta fonte é usada.
 */
import type { Agent, AgentState, AgentStatus, DeptStatus } from "./types";

const ROTEIRO: AgentState[] = ["idle", "working", "thinking", "working", "completed", "idle", "waiting", "idle"];

const TAREFAS_DEMO: Record<string, string[]> = {
  coordenador: ["Distribuir a fila da hora", "Conferir agendamentos"],
  "rpi-monitor": ["Verificar índice da RPI", "Comparar com edições já importadas"],
  "rpi-coletor": ["Baixar RM.zip da edição", "Conferir hash do arquivo"],
  parser: ["Ler processos do XML", "Gravar oportunidades"],
  "inpi-planejador": ["Selecionar processos elegíveis"],
  "inpi-verificador": ["Consultar processo no pePI", "Ler representante legal"],
  cnpj: ["Varrer base de empresas", "Cruzar titular com CNPJ"],
  sites: ["Ler site oficial do titular", "Confirmar vínculo pelo CNPJ"],
  "pesquisa-ia": ["Pesquisar contatos comerciais"],
  validador: ["Conferir e-mail na página de origem", "Validar telefone"],
  qualificador: ["Calcular score dos leads", "Deduplicar por CNPJ"],
  redator: ["Escrever sugestão de abordagem"],
  relator: ["Consolidar relatório da semana"],
};

/** Estado de demonstração de um agente num dado "tique" (determinístico). */
export function demoStatus(agent: Agent, index: number, tick: number, now: number): AgentStatus {
  const passo = (tick + index * 3) % ROTEIRO.length;
  let state = ROTEIRO[passo];
  // um único erro roteirizado, para mostrar o estado ERROR
  if (agent.id === "inpi-verificador" && tick % 24 >= 20) state = "error";
  if (agent.modelo.startsWith("claude") && state !== "idle") state = "waiting"; // IA desligada na demonstração
  const tarefas = TAREFAS_DEMO[agent.id] ?? ["Tarefa de demonstração"];
  const tarefa = state === "idle" ? null
    : state === "error" ? "Consulta interrompida (simulação)"
      : state === "waiting" && agent.modelo.startsWith("claude") ? "Aguardando chave de API (simulação)"
        : tarefas[Math.floor((tick + index) / ROTEIRO.length) % tarefas.length];
  return { state, tarefa, desde: now - ((tick + index) % 5) * 1000, fonte: "demo" };
}

export function deptStatus(statuses: AgentStatus[]): DeptStatus {
  const ativos = statuses.filter((s) => s.state === "working" || s.state === "thinking").length;
  const estado: DeptStatus["estado"] = statuses.some((s) => s.state === "error") ? "Atenção"
    : ativos > 0 ? "Em atividade"
      : statuses.some((s) => s.state === "waiting") ? "Aguardando" : "Disponível";
  return { estado, ativos, tarefas: statuses.filter((s) => s.tarefa).length };
}

export const DEPT_ESTADO_COR: Record<DeptStatus["estado"], string> = {
  "Disponível": "#94a3b8", "Em atividade": "#22c55e", "Aguardando": "#f59e0b", "Atenção": "#ef4444",
};
