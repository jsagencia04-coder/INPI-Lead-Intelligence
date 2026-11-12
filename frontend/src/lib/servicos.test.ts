import { describe, expect, it } from "vitest";
import { CLASSE, SERVICO, diasRestantes, textoPrazo } from "./servicos";

describe("oportunidades de serviço", () => {
  it("separa as duas frentes comerciais", () => {
    expect(SERVICO.manifestacao_oposicao.rotulo).toBe("Manifestação à oposição");
    expect(SERVICO.recurso_indeferimento.rotulo).toBe("Recurso contra indeferimento");
    expect(Object.keys(CLASSE)).toEqual(["quente", "morno", "pendente", "historico"]);
  });
  it("conta os dias até o vencimento estimado", () => {
    const hoje = new Date(2026, 10, 12);
    expect(diasRestantes("2027-01-11", hoje)).toBe(60);
    expect(diasRestantes("2026-11-03", hoje)).toBe(-9);
    expect(textoPrazo({ prazo_fim: "2026-12-07", prazo_status: "em_andamento" }, hoje)).toBe("25 dia(s) restantes");
    expect(textoPrazo({ prazo_fim: "2026-11-03", prazo_status: "encerrado" }, hoje)).toBe("Encerrado há 9 dia(s)");
    expect(textoPrazo({ prazo_fim: null, prazo_status: "validar" }, hoje)).toBe("Prazo a validar");
  });
});
