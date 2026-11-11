export function fmtDate(v: string | null | undefined) {
  if (!v) return "—";
  return new Date(v).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export const procuradorLabel: Record<string, string> = {
  com_procurador: "Com procurador",
  sem_confirmado: "Sem procurador (confirmado no INPI)",
  sem_na_rpi: "Sem procurador na RPI (não confirmado)",
  desconhecido: "Desconhecido",
};

export const jobStatusLabel: Record<string, string> = {
  queued: "Na fila",
  running: "Executando",
  succeeded: "Concluído",
  failed: "Falhou",
  dead: "Falhou (revisar)",
  cancelled: "Cancelado",
};

export const categoriaLabel: Record<string, string> = {
  oposicao: "Oposição",
  exigencia: "Exigência",
  indeferimento: "Indeferimento",
  extincao_prorrogacao: "Extinção (vigência/prorrogação)",
  arquivamento: "Arquivamento",
  outro: "Outro",
};

export const editionStatusLabel: Record<string, string> = {
  detected: "Detectada",
  downloading: "Baixando",
  downloaded: "Baixada",
  parsing: "Interpretando",
  parsed: "Processada",
  error: "Erro",
};

export function fmtBytes(n: number) {
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.round(n / 1e3)} KB`;
}

export function fmtNum(n: number | undefined | null) {
  return n == null ? "—" : n.toLocaleString("pt-BR");
}

export const procuradorCurto: Record<string, string> = {
  com_procurador: "Com procurador",
  sem_confirmado: "Sem (confirmado)",
  sem_na_rpi: "Sem na RPI",
  desconhecido: "Desconhecido",
};

export const leadStatusLabel: Record<string, string> = {
  novo: "Novo",
  pesquisando: "Pesquisando",
  sem_contato: "Sem contato",
  qualificado: "Qualificado",
  em_revisao: "Em revisão",
  aprovado: "Aprovado",
  contatado: "Contatado",
  convertido: "Convertido",
  descartado: "Descartado",
};

export const verificacaoLabel: Record<string, string> = {
  encontrado: "Encontrado",
  formato_ok: "Formato válido",
  dominio_ok: "Validado (automático)",
  verificado_humano: "Verificado por pessoa",
  invalido: "Inválido",
};

export const prioridadeVariant: Record<string, "default" | "secondary" | "outline" | "destructive"> = {
  alta: "default",
  media: "secondary",
  baixa: "outline",
};

export function fmtDay(v: string | null | undefined) {
  if (!v) return "—";
  const [y, m, d] = v.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

export function diasAte(v: string | null | undefined): number | null {
  if (!v) return null;
  const ms = new Date(v.slice(0, 10) + "T00:00:00").getTime() - new Date(new Date().toDateString()).getTime();
  return Math.round(ms / 86400000);
}
