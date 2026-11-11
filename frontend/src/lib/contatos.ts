/** Central de contatos: tipos, rótulos e funções puras (testadas). */

export type WaNivel = "found" | "candidate" | "company_evidence" | "human_confirmed" | "invalid";

export type ContatoCentral = {
  id: number;
  tipo: string;
  valor: string;
  valor_normalizado: string;
  verificacao: "encontrado" | "formato_ok" | "dominio_ok" | "verificado_humano" | "invalido";
  confianca: number | null;
  fonte_tipo: "web" | "receita" | "manual";
  fonte_url: string | null;
  fonte_titulo: string | null;
  fonte_trecho: string | null;
  fonte_obtida_em: string | null;
  observacao: string | null;
  created_at: string;
  eh_celular: boolean | null;
  wa_nivel: WaNivel | null;
  wa_conta: "desconhecido" | "confirmada" | "inexistente";
  wa_comercial: "desconhecido" | "publicado_pela_empresa" | "confirmado" | "nao";
  bloqueado: boolean;
  com_permissao: boolean;
};

export type TitularCentral = {
  holder_id: number;
  titular: string;
  tipo_provavel: string;
  uf: string | null;
  cnpj: string | null;
  cnpj_status: string;
  razao_social: string | null;
  nome_fantasia: string | null;
  lead_id: number | null;
  lead_status: string | null;
  marcas: string | null;
  processos: string | null;
  contatos: ContatoCentral[];
  n_contatos: number;
  n_invalidos: number;
  n_bloqueados: number;
  titular_bloqueado: boolean;
  pesquisado_em: string | null;
};

export const FILTROS: Record<string, string> = {
  todos: "Todos os contatos",
  whatsapp: "Somente WhatsApp",
  wa_candidato: "WhatsApp candidatos",
  wa_empresa: "WhatsApp com evidência empresarial",
  wa_humano: "WhatsApp confirmado manualmente",
  telefones: "Telefones",
  emails: "E-mails",
  sem_contatos: "Sem contatos",
  pendentes: "Contatos pendentes",
  invalidos: "Contatos inválidos",
  leads_aprovados: "Leads aprovados",
  com_permissao: "Com permissão de comunicação",
  bloqueados: "Contatos bloqueados",
};

export const ORDENS: Record<string, string> = {
  titular: "Titular (A–Z)",
  pesquisa: "Data da pesquisa",
  confianca: "Confiança",
  score: "Score do lead",
  contatos: "Nº de contatos",
};

export const WA_NIVEL: Record<WaNivel, { rotulo: string; dica: string; cor: string }> = {
  found: { rotulo: "encontrado", dica: "Número encontrado, ainda sem checagem.", cor: "text-slate-600" },
  candidate: { rotulo: "candidato", dica: "Celular válido, sem prova de que tem WhatsApp.", cor: "text-amber-700" },
  company_evidence: { rotulo: "evidência empresarial", dica: "A própria empresa publica o número como WhatsApp.", cor: "text-emerald-700" },
  human_confirmed: { rotulo: "confirmado por pessoa", dica: "Uma pessoa confirmou a conta e o vínculo com a empresa.", cor: "text-emerald-700" },
  invalid: { rotulo: "inválido", dica: "Número inválido ou incorreto.", cor: "text-destructive" },
};

export const VERIFICACAO: Record<ContatoCentral["verificacao"], string> = {
  encontrado: "encontrado",
  formato_ok: "formato válido",
  dominio_ok: "validado na fonte",
  verificado_humano: "confirmado por pessoa",
  invalido: "inválido",
};

/** Rótulo do status: para WhatsApp vale o nível próprio; para os demais, a verificação. */
export function statusContato(c: ContatoCentral): string {
  return c.tipo === "whatsapp" && c.wa_nivel ? WA_NIVEL[c.wa_nivel].rotulo : VERIFICACAO[c.verificacao];
}

/** Melhor contato válido de um tipo (a API já entrega do melhor para o pior). */
export function melhor(contatos: ContatoCentral[], tipo: string): ContatoCentral | undefined {
  return contatos.find((c) => c.tipo === tipo && c.verificacao !== "invalido");
}

export function quantos(contatos: ContatoCentral[], tipo: string): number {
  return contatos.filter((c) => c.tipo === tipo && c.verificacao !== "invalido").length;
}

/** Origem legível; só devolve link quando a fonte é uma página real. */
export function origem(c: ContatoCentral): { texto: string; href: string | null } {
  if (c.fonte_url && /^https?:\/\//i.test(c.fonte_url)) {
    let host = c.fonte_url;
    try { host = new URL(c.fonte_url).hostname.replace(/^www\./, ""); } catch { /* mantém a URL */ }
    return { texto: host, href: c.fonte_url };
  }
  if (c.fonte_tipo === "receita") return { texto: "Receita Federal (CNPJ)", href: null };
  if (c.fonte_tipo === "manual") return { texto: "Cadastro manual", href: null };
  return { texto: c.fonte_url ?? "sem fonte", href: null };
}

export function fmtCnpj(c: string | null): string {
  const m = (c ?? "").match(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/);
  return m ? `${m[1]}.${m[2]}.${m[3]}/${m[4]}-${m[5]}` : (c ?? "");
}
