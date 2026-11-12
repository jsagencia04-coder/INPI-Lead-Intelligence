/** Converte o estado real do backend (/api/office/state) para o modelo da cena. Funções puras (testáveis). */
import { AGENTES, DEPARTAMENTOS } from "./config";
import { deptStatus } from "./demo";
import type { Agent, AgentState, AgentStatus, DeptStatus } from "./types";

export type TipoEstado = {
  state: AgentState; tarefa: string | null; desde: string | null;
  pendentes: number; agendados: number; executando: number; concluidos_hoje: number; falhas_hoje: number;
  ultimo: { job_id: number; status: string; em: string | null; resultado: unknown; erro: string | null; tarefa: string } | null;
};
export type OfficeState = {
  gerado_em: string;
  tipos: Record<string, TipoEstado>;
  kpis: { pendentes: number; executando: number; concluidas_hoje: number; falhas_hoje: number; leads: number; leads_whatsapp?: number;
    tokens_semana: number; custo_semana_usd: number; ultimo_evento_id: number };
  sistema: { worker_ok: boolean; agendamentos_atrasados: string[]; ia_configurada: boolean };
};
export type OfficeEvent = {
  id: number; tipo: string; agente: string; job_id: number | null; referencia: string | null;
  descricao: string; resultado: Record<string, unknown> | null; criado_em: string;
};

// prioridade para juntar vários tipos de job num mesmo personagem
const PESO: Record<AgentState, number> = { error: 6, working: 5, thinking: 5, waiting: 3, completed: 2, idle: 1 };

export function agentStatusFromReal(agent: Agent, st: OfficeState): AgentStatus {
  const tipos = (agent.id === "coordenador" ? agent.jobTypes.filter((t) => t !== "system.ping") : agent.jobTypes).map((t) => st.tipos[t]).filter(Boolean);
  if (!tipos.length) return { state: "idle", tarefa: null, desde: Date.parse(st.gerado_em), fonte: "real" };
  const top = tipos.reduce((a, b) => (PESO[b.state] > PESO[a.state] ? b : a));
  return { state: top.state, tarefa: top.tarefa, desde: top.desde ? Date.parse(top.desde) : Date.parse(st.gerado_em), fonte: "real" };
}

export function realOffice(st: OfficeState) {
  const statuses: Record<string, AgentStatus> = {};
  AGENTES.forEach((a) => { statuses[a.id] = agentStatusFromReal(a, st); });
  const depts: Record<string, DeptStatus> = {};
  DEPARTAMENTOS.forEach((d) => {
    const ags = AGENTES.filter((a) => a.departamento === d.id);
    const base = deptStatus(ags.map((a) => statuses[a.id]));
    // tarefas reais do setor: em execução + prontas na fila
    const tarefas = ags.flatMap((a) => a.jobTypes).reduce((n, t) => n + (st.tipos[t]?.executando ?? 0) + (st.tipos[t]?.pendentes ?? 0), 0);
    depts[d.id] = { ...base, tarefas };
  });
  return { statuses, depts };
}

/** Personagem e departamento responsáveis por um evento (pelo tipo de job). */
export function agentOfEvent(ev: Pick<OfficeEvent, "agente">): Agent | undefined {
  return AGENTES.find((a) => a.jobTypes.includes(ev.agente) || (ev.agente === "scheduler" && a.id === "coordenador"));
}

export function mergeEvents(atual: OfficeEvent[], novos: OfficeEvent[], max = 200): OfficeEvent[] {
  if (!novos.length) return atual;
  const ids = new Set(atual.map((e) => e.id));
  return [...atual, ...novos.filter((e) => !ids.has(e.id))].sort((a, b) => a.id - b.id).slice(-max);
}
