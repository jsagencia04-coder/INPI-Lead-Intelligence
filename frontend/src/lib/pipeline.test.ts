import { describe, expect, it } from "vitest";
import { ETAPAS, FASES, porFase } from "./pipeline";
import { NAV, TODOS, itemAtual } from "./nav";

describe("pipeline e navegação", () => {
  it("17 etapas, cada uma em uma fase, somas por fase", () => {
    expect(ETAPAS).toHaveLength(17);
    expect(new Set(ETAPAS.map((e) => e.fase))).toEqual(new Set(FASES));
    const f = porFase([{ chave: "lead_novo", n: 3 }, { chave: "contato_validado", n: 2 }, { chave: "fechado", n: 1 }]);
    expect(f.find((x) => x.fase === "Identificação")!.total).toBe(5);
    expect(f.find((x) => x.fase === "Resultado")!.total).toBe(1);
    expect(f.reduce((s, x) => s + x.total, 0)).toBe(6);
  });
  it("menu cobre todas as telas existentes, sem duplicar", () => {
    const hrefs = TODOS.map((i) => i.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    for (const h of ["/", "/escritorio", "/pipeline", "/leads", "/contatos", "/whatsapp", "/rpi", "/processos", "/despachos",
      "/revisoes", "/jobs", "/relatorios", "/operacao", "/usuarios"]) expect(hrefs).toContain(h);
    expect(NAV.length).toBeGreaterThanOrEqual(4);
  });
  it("identifica o módulo pela rota, inclusive subpáginas", () => {
    expect(itemAtual("/")?.item.label).toBe("Painel executivo");
    expect(itemAtual("/leads/42")?.item.href).toBe("/leads");
    expect(itemAtual("/escritorio")?.grupo).toBe("Visão geral");
    expect(itemAtual("/inexistente")).toBeNull();
  });
});
