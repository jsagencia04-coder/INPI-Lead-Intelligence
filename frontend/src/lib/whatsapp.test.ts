import { describe, expect, it } from "vitest";
import { formatWhats, mensagemInicial } from "./whatsapp";

const lead = (categoria: string) => ({
  categoria_principal: categoria,
  processos: [{ numero_processo: "945424620", marca_nome: "MARCA ALFA",
    ultimo_despacho: { rpi: 2914, data_publicacao: "2026-11-10" } }],
});

describe("WhatsApp", () => {
  it("formata número brasileiro", () => {
    expect(formatWhats("+5511988887777")).toBe("(11) 98888-7777");
    expect(formatWhats("+551133334444")).toBe("(11) 3333-4444");
  });
  it("mensagem usa só fatos do processo e tem opt-out", () => {
    const m = mensagemInicial(lead("oposicao"), "Júlio");
    expect(m).toContain("Aqui é Júlio");
    expect(m).toContain("RPI nº 2914 (10/11/2026)");
    expect(m).toContain('marca "MARCA ALFA" (processo 945424620)');
    expect(m).toContain("responder SAIR");
  });
  it("texto específico por categoria", () => {
    expect(mensagemInicial(lead("indeferimento"), "J")).toContain("recorrer em até 60 dias");
    expect(mensagemInicial(lead("exigencia"), "J")).toContain("exigência do INPI");
    expect(mensagemInicial(lead("extincao_prorrogacao"), "J")).toContain("sem proteção");
  });
  it("sem assinatura deixa marcador visível", () => {
    expect(mensagemInicial(lead("oposicao"), "")).toContain("[seu nome]");
  });
});
