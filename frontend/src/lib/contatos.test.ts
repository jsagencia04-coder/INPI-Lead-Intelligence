import { describe, expect, it } from "vitest";
import { fmtCnpj, melhor, origem, quantos, statusContato, type ContatoCentral } from "./contatos";

const base: ContatoCentral = {
  id: 1, tipo: "whatsapp", valor: "(11) 98888-7777", valor_normalizado: "+5511988887777", verificacao: "formato_ok",
  confianca: 0.35, fonte_tipo: "web", fonte_url: "https://www.empresa.com.br/contato", fonte_titulo: null, fonte_trecho: null,
  fonte_obtida_em: null, observacao: null, created_at: "2026-11-11T00:00:00Z", eh_celular: true, wa_nivel: "candidate",
  wa_conta: "desconhecido", wa_comercial: "desconhecido", bloqueado: false, com_permissao: false,
};

describe("central de contatos", () => {
  it("WhatsApp usa o nível próprio; outros tipos usam a verificação", () => {
    expect(statusContato(base)).toBe("candidato");
    expect(statusContato({ ...base, wa_nivel: "company_evidence" })).toBe("evidência empresarial");
    expect(statusContato({ ...base, tipo: "telefone", wa_nivel: null })).toBe("formato válido");
  });
  it("ignora inválidos ao escolher o melhor contato", () => {
    const lista = [{ ...base, id: 1, verificacao: "invalido" as const }, { ...base, id: 2 }];
    expect(melhor(lista, "whatsapp")?.id).toBe(2);
    expect(quantos(lista, "whatsapp")).toBe(1);
    expect(melhor(lista, "email")).toBeUndefined();
  });
  it("só cria link para página real; Receita não é link", () => {
    expect(origem(base)).toEqual({ texto: "empresa.com.br", href: "https://www.empresa.com.br/contato" });
    expect(origem({ ...base, fonte_tipo: "receita", fonte_url: "receita:12345678000190" }).href).toBeNull();
    expect(origem({ ...base, fonte_url: "javascript:alert(1)" }).href).toBeNull();
  });
  it("formata CNPJ", () => expect(fmtCnpj("12345678000190")).toBe("12.345.678/0001-90"));
});
