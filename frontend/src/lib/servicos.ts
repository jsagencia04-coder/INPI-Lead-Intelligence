/** V2.4 · Oportunidades de serviço: (1) manifestação à oposição; (2) recurso contra indeferimento. */

export type Servico = "manifestacao_oposicao" | "recurso_indeferimento";
export type Classe = "quente" | "morno" | "historico" | "pendente";
export type PrazoStatus = "em_andamento" | "proximo_fim" | "encerrado" | "validar";

export type Oportunidade = {
  id: number;
  numero_processo: string;
  servico: Servico;
  tipo_decisao: "oposicao" | "indeferimento" | "deferimento_parcial";
  rpi_numero: number;
  despacho_codigo: string;
  data_publicacao: string | null;
  elegivel: boolean;
  fundamentacao: string | null;
  oposicao_protocolo: string | null;
  oposicao_data: string | null;
  opositor_nome: string | null;
  opositor_fonte: string | null;
  prazo_inicio: string | null;
  prazo_fim: string | null;
  prazo_status: PrazoStatus;
  prazo_fonte: string | null;
  validacao_juridica: boolean;
  validacao_motivo: string | null;
  medida_status: "nao_verificada" | "nao_identificada" | "protocolada";
  medida_protocolo: string | null;
  medida_data: string | null;
  medida_fonte: string | null;
  decisao_posterior: string | null;
  situacao_processual: "aberta" | "historico" | "pendente";
  classificacao: Classe | null;
  classificacao_motivos: string[];
  marca_nome: string | null;
  classes_nice?: string[] | null;
  situacao_atual?: string | null;
  holder_id?: number;
  titular?: string;
  tipo_provavel?: string;
  cnpj?: string | null;
  geo_uf?: string | null;
  geo_municipio?: string | null;
  geo_status?: string | null;
  lead_id?: number | null;
  pipeline_stage?: string | null;
  contatos?: number;
  contatos_validados?: number;
};

export type Indicadores = {
  identificadas: number; titulares: number; abertas: number; protocoladas: number; historico: number;
  quentes: number; mornos: number; pendentes: number; qualificados: number; contatos_encontrados: number;
  abordados: number; proximos_fim: number; validacao_juridica: number; parciais: number; proximo_vencimento?: string | null;
};
export type Painel = {
  manifestacao_oposicao: Indicadores;
  recurso_indeferimento: Indicadores;
  consolidado: Omit<Indicadores, "proximo_vencimento">;
  melhores: Oportunidade[];
};
export type ResumoExecutivo = {
  texto: string;
  destaques: { uf: string; manifestacoes_abertas: number; recursos_abertos: number; manifestacoes_quentes: number; recursos_quentes: number; prazos_curtos: number }[];
  melhores: Oportunidade[];
  indicadores: Painel;
};
export type ServicosUF = {
  oposicoes_sofridas: number; manifestacoes_cabiveis: number; manifestacoes_protocoladas: number;
  indeferimentos: number; recursos_cabiveis: number; recursos_protocolados: number;
  contatos_encontrados: number; leads_quentes: number;
  melhores: Record<Servico, Oportunidade[]>;
  municipios: { municipio: string; oposicoes: number; indeferimentos: number }[];
};

export const SERVICO: Record<Servico, { rotulo: string; curto: string; oferta: string; classe: string; hex: string }> = {
  manifestacao_oposicao: {
    rotulo: "Manifestação à oposição", curto: "Manifestação", oferta: "Defesa do pedido de registro de marca",
    classe: "bg-violet-500/12 text-violet-700 dark:text-violet-300", hex: "#7c3aed",
  },
  recurso_indeferimento: {
    rotulo: "Recurso contra indeferimento", curto: "Recurso", oferta: "Recurso administrativo contra indeferimento de marca",
    classe: "bg-sky-500/12 text-sky-700 dark:text-sky-300", hex: "#0284c7",
  },
};

export const CLASSE: Record<Classe, { rotulo: string; dica: string; classe: string; ponto: string }> = {
  quente: { rotulo: "Quente", dica: "Prazo aberto, nenhuma petição no INPI, contato validado e sem abordagem anterior", classe: "bg-rose-500/12 text-rose-700 dark:text-rose-300", ponto: "bg-rose-500" },
  morno: { rotulo: "Morno", dica: "Relevante, mas depende de confirmação (petições, contato ou validação jurídica)", classe: "bg-amber-500/15 text-amber-800 dark:text-amber-300", ponto: "bg-amber-500" },
  pendente: { rotulo: "Pendente", dica: "Informações processuais ou comerciais insuficientes", classe: "bg-slate-500/12 text-slate-700 dark:text-slate-300", ponto: "bg-slate-400" },
  historico: { rotulo: "Histórico", dica: "Prazo encerrado, medida já apresentada ou decisão posterior", classe: "bg-zinc-500/10 text-zinc-600 dark:text-zinc-400", ponto: "bg-zinc-400" },
};

export const PRAZO: Record<PrazoStatus, { rotulo: string; classe: string }> = {
  em_andamento: { rotulo: "Prazo em andamento", classe: "text-emerald-700 dark:text-emerald-300" },
  proximo_fim: { rotulo: "Próximo do encerramento", classe: "text-amber-700 dark:text-amber-300" },
  encerrado: { rotulo: "Prazo encerrado", classe: "text-zinc-500" },
  validar: { rotulo: "Validar prazo", classe: "text-slate-600" },
};

export const MEDIDA: Record<Oportunidade["medida_status"], string> = {
  protocolada: "Já protocolada",
  nao_identificada: "Nenhuma no pePI",
  nao_verificada: "Ainda não conferida",
};

export const TIPO_DECISAO: Record<Oportunidade["tipo_decisao"], string> = {
  oposicao: "Oposição sofrida",
  indeferimento: "Indeferimento",
  deferimento_parcial: "Deferimento parcial",
};

/** Dias até o vencimento (negativo = vencido). */
export function diasRestantes(fim: string | null, hoje: Date = new Date()): number | null {
  if (!fim) return null;
  const [y, m, d] = fim.slice(0, 10).split("-").map(Number);
  const alvo = Date.UTC(y, m - 1, d);
  const base = Date.UTC(hoje.getFullYear(), hoje.getMonth(), hoje.getDate());
  return Math.round((alvo - base) / 86400000);
}

export function textoPrazo(o: Pick<Oportunidade, "prazo_fim" | "prazo_status">, hoje?: Date): string {
  if (o.prazo_status === "validar" || !o.prazo_fim) return "Prazo a validar";
  const r = diasRestantes(o.prazo_fim, hoje)!;
  if (r < 0) return `Encerrado há ${-r} dia(s)`;
  if (r === 0) return "Vence hoje";
  return `${r} dia(s) restantes`;
}
