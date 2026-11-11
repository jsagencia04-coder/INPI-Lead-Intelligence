import { describe, expect, it } from "vitest";
import { AGENTES, DEPARTAMENTOS, ROOM_D, ROOM_W } from "./config";
import { demoStatus, deptStatus } from "./demo";
import { iso, isoBox, shade, zoomAt } from "./iso";

describe("projeção isométrica", () => {
  it("converte tiles em pixels (2:1)", () => {
    expect(iso(0, 0)).toEqual({ x: 0, y: 0 });
    expect(iso(1, 0)).toEqual({ x: 32, y: 16 });
    expect(iso(0, 1)).toEqual({ x: -32, y: 16 });
    expect(iso(1, 1, 10)).toEqual({ x: 0, y: 22 });
  });
  it("gera as três faces visíveis de uma caixa", () => {
    const b = isoBox(0, 0, 1, 1, 10);
    expect(b.top.split(" ")).toHaveLength(4);
    expect(b.top).toContain("0,-10");
  });
  it("zoom fica nos limites e mantém o ponto sob o cursor", () => {
    const v = zoomAt({ x: 0, y: 0, s: 1 }, 2, 100, 100);
    expect(v).toEqual({ s: 2, x: -100, y: -100 });
    expect(zoomAt({ x: 0, y: 0, s: 1 }, 100, 0, 0).s).toBe(3);
    expect(zoomAt({ x: 0, y: 0, s: 1 }, 0.01, 0, 0).s).toBe(0.35);
  });
  it("shade clareia e escurece", () => {
    expect(shade("#000000", 1)).toBe("#ffffff");
    expect(shade("#ffffff", -1)).toBe("#000000");
  });
});

describe("configuração", () => {
  it("tem os 8 departamentos pedidos e todo agente pertence a um deles", () => {
    expect(DEPARTAMENTOS.map((d) => d.nome)).toEqual(
      ["Diretoria", "RPI", "Processamento", "INPI", "Investigação", "Validação", "Comercial", "Relatórios"]);
    const ids = new Set(DEPARTAMENTOS.map((d) => d.id));
    for (const a of AGENTES) expect(ids.has(a.departamento)).toBe(true);
  });
  it("todo departamento tem ao menos um agente e as mesas cabem na sala", () => {
    for (const d of DEPARTAMENTOS) {
      const ags = AGENTES.filter((a) => a.departamento === d.id);
      expect(ags.length).toBeGreaterThan(0);
      for (const a of ags) {
        expect(a.mesa.x + 2).toBeLessThanOrEqual(ROOM_W);
        expect(a.mesa.y + 2).toBeLessThanOrEqual(ROOM_D);
      }
    }
  });
  it("cada tipo de job real aparece em um único personagem", () => {
    const todos = AGENTES.flatMap((a) => a.jobTypes);
    expect(new Set(todos).size).toBe(todos.length);
    for (const t of ["rpi.discover", "rpi.collect", "rpi.parse", "inpi.verify", "cnpj.sync", "research.free",
      "research.holder", "lead.validate_contacts", "leads.build", "sales.summarize_batch", "reports.weekly"]) {
      expect(todos).toContain(t);
    }
  });
});

describe("demonstração", () => {
  it("é determinística e sempre marcada como demo", () => {
    const a = demoStatus(AGENTES[1], 1, 7, 1000);
    expect(demoStatus(AGENTES[1], 1, 7, 1000)).toEqual(a);
    expect(a.fonte).toBe("demo");
  });
  it("passa por todos os estados ao longo do roteiro", () => {
    const vistos = new Set<string>();
    for (let t = 0; t < 48; t++) AGENTES.forEach((a, i) => vistos.add(demoStatus(a, i, t, 0).state));
    expect([...vistos].sort()).toEqual(["completed", "error", "idle", "thinking", "waiting", "working"]);
  });
  it("agentes de IA ficam aguardando (sem chave) na demonstração", () => {
    const ia = AGENTES.filter((a) => a.modelo.startsWith("claude"));
    for (let t = 0; t < 16; t++) for (const a of ia) expect(["idle", "waiting"]).toContain(demoStatus(a, 0, t, 0).state);
  });
  it("estado do departamento", () => {
    const s = (state: string, tarefa: string | null = "x") => ({ state, tarefa, desde: 0, fonte: "demo" }) as never;
    expect(deptStatus([s("idle", null)]).estado).toBe("Disponível");
    expect(deptStatus([s("working"), s("idle", null)])).toEqual({ estado: "Em atividade", ativos: 1, tarefas: 1 });
    expect(deptStatus([s("waiting")]).estado).toBe("Aguardando");
    expect(deptStatus([s("working"), s("error")]).estado).toBe("Atenção");
  });
});

import { agentOfEvent, agentStatusFromReal, mergeEvents, realOffice, type OfficeState } from "./real";

const estadoReal = (tipos: Record<string, Partial<OfficeState["tipos"][string]>>): OfficeState => ({
  gerado_em: "2026-11-11T12:00:00Z",
  tipos: Object.fromEntries(Object.entries(tipos).map(([k, v]) => [k, {
    state: "idle", tarefa: null, desde: null, pendentes: 0, agendados: 0, executando: 0, concluidos_hoje: 0,
    falhas_hoje: 0, ultimo: null, ...v }])) as OfficeState["tipos"],
  kpis: { pendentes: 0, executando: 0, concluidas_hoje: 0, falhas_hoje: 0, leads: 0, tokens_semana: 0, custo_semana_usd: 0, ultimo_evento_id: 0 },
  sistema: { worker_ok: true, agendamentos_atrasados: [], ia_configurada: false },
});

describe("dados reais", () => {
  it("personagem com vários tipos de job mostra o estado mais importante", () => {
    const sergio = AGENTES.find((a) => a.id === "sites")!;
    const st = estadoReal({ "research.free_batch": { state: "completed" }, "research.free": { state: "working", tarefa: "Pesquisando" } });
    const s = agentStatusFromReal(sergio, st);
    expect(s).toMatchObject({ state: "working", tarefa: "Pesquisando", fonte: "real" });
    expect(agentStatusFromReal(sergio, estadoReal({ "research.free": { state: "error" }, "research.free_batch": { state: "working" } })).state).toBe("error");
  });
  it("sem dados de um tipo, o personagem fica IDLE (nada é inventado)", () => {
    expect(agentStatusFromReal(AGENTES[3], estadoReal({})).state).toBe("idle");
  });
  it("coordenadora reflete o agendador", () => {
    const clara = AGENTES.find((a) => a.id === "coordenador")!;
    expect(agentStatusFromReal(clara, estadoReal({ scheduler: { state: "error", tarefa: "Worker parado" } })).state).toBe("error");
  });
  it("tarefas do departamento somam execução e fila reais", () => {
    const { depts } = realOffice(estadoReal({ "inpi.verify": { state: "working", executando: 1, pendentes: 40 } }));
    expect(depts.inpi).toMatchObject({ estado: "Em atividade", tarefas: 41, ativos: 1 });
    expect(depts.rpi.tarefas).toBe(0);
  });
  it("eventos: agente responsável e junção sem duplicar", () => {
    expect(agentOfEvent({ agente: "inpi.verify" })?.nome).toBe("Vítor");
    expect(agentOfEvent({ agente: "desconhecido" })).toBeUndefined();
    const e = (id: number) => ({ id, tipo: "t", agente: "a", job_id: null, referencia: null, descricao: "", resultado: null, criado_em: "" });
    expect(mergeEvents([e(1), e(2)], [e(2), e(3)]).map((x) => x.id)).toEqual([1, 2, 3]);
    expect(mergeEvents([], [e(1), e(2), e(3)], 2).map((x) => x.id)).toEqual([2, 3]);
  });
});
