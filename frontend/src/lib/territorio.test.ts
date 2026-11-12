import { describe, expect, it } from "vitest";
import { BRASIL_UFS } from "./brasil-geo";
import { degrau, responsavel } from "./territorio";

describe("mapa e operação semanal", () => {
  it("mapa tem os 26 estados e o DF, sem repetição", () => {
    const ufs = BRASIL_UFS.map((u) => u.uf);
    expect(new Set(ufs).size).toBe(27);
    for (const u of ["SC", "RS", "PR", "DF", "SP", "AM", "RR"]) expect(ufs).toContain(u);
    for (const u of BRASIL_UFS) expect(u.path.length).toBeGreaterThan(50);
  });
  it("zero é zero (sem cor) e o máximo cai no último degrau", () => {
    expect(degrau(0, 10)).toBe(-1);
    expect(degrau(10, 10)).toBe(4);
    expect(degrau(1, 10)).toBe(0);
    expect(degrau(5, 0)).toBe(-1);
  });
  it("responsável pela fase segue os números reais", () => {
    const b = { uf: "SC", leads: 3, processos: 3, oposicoes: 2, publicados_oposicao: 1, verificados_inpi: 1, quentes: 0, mornos: 0,
      com_contato_validado: 0, pesquisados: 0, pendencias_validacao: 0, tarefas_ativas: 2, falhas: 0 };
    expect(responsavel(b)).toMatch(/Vítor/);
    expect(responsavel({ ...b, verificados_inpi: 3 })).toMatch(/Sérgio/);
    expect(responsavel({ ...b, verificados_inpi: 3, pesquisados: 3, pendencias_validacao: 1 })).toMatch(/Valéria/);
    expect(responsavel({ ...b, falhas: 1 })).toMatch(/Revisão/);
  });
});
