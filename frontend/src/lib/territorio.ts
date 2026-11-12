/** Tipos e rótulos do Mapa de Oportunidades e da Central RPI (V2.3). */
export type IndicadoresUF = {
  uf: string; leads: number; oposicoes_apresentadas: number; publicados_oposicao: number; com_contato_validado: number;
  quentes: number; mornos: number; em_pesquisa: number; novos_ultima_rpi: number; em_analise: number; trabalhados: number;
  localizacao_confirmada: number; localizacao_estimada: number; ordem_prioridade: number | null; taxa_qualificacao: number | null;
};
export type Mapa = { processado: boolean; ultima_edicao: number | null; processado_em: string | null; estados: IndicadoresUF[]; pendente: IndicadoresUF; total: number };
export type LeadPrioritario = {
  id: number; titular: string; municipio: string | null; geo_status: string; score: number | null; temperatura: string | null;
  temperatura_motivos: string[]; whatsapp: string | null; whatsapp_status: string | null; categoria_principal: string | null; tem_a: boolean; marcas: string | null;
};
export type PainelUF = {
  uf: string; info: { nome: string; regiao: string; ordem: number } | null;
  indicadores: IndicadoresUF & { titulares: number; empresas: number };
  prioritarios: LeadPrioritario[]; municipios: { chave: string; n: number }[];
  historico: { numero: number; data_publicacao: string | null; leads: number; oposicoes_apresentadas: number; publicados_oposicao: number; quentes: number; abordagens: number }[];
  pipeline: { chave: string; n: number }[];
};

export type StatusEtapa = "sem_dados" | "pendente" | "em_execucao" | "concluida" | "erro";
export type UFSemana = {
  uf: string; leads: number; processos: number; oposicoes: number; publicados_oposicao: number; verificados_inpi: number;
  quentes: number; mornos: number; com_contato_validado: number; pesquisados: number; pendencias_validacao: number; tarefas_ativas: number; falhas: number;
};
export type Operacao = {
  edicao: { numero: number; data_publicacao: string | null; status: string; detectada_em: string; coletada_em: string | null; processada_em: string | null };
  operacao: { iniciada_em: string; priorizada_em: string | null; sc_primeiros_quentes_em: string | null; concluida_em: string | null; ultima_verificacao_em: string | null; execucoes: number } | null;
  etapas: { chave: string; nome: string; status: StatusEtapa; em?: string | null; dados?: Partial<UFSemana> | null }[];
  trabalhando_em: string | null;
  ufs: UFSemana[];
  ultima_verificacao_rpi: string | null;
  atraso: { desde: string; terca: string; horas: number } | null;
};
export type Semana = {
  status: Operacao | null;
  edicoes: { numero: number; data_publicacao: string | null; status: string }[];
  agenda: { nome: string; ativo: boolean; proximo_em: string; intervalo_minutos: number; dias_semana: number[] | null; hora_inicio: string | null; hora_fim: string | null }[];
  execucoes: { id: number; tipo: string; status: string; criado_em: string; finalizado_em: string | null; tentativas: number; erro: string }[];
};
export type Relatorio = {
  uf: string; edicao: Operacao["edicao"]; situacao: StatusEtapa; oposicoes: number; publicados_oposicao: number; novas_oportunidades: number;
  contatos_validados: number; leads_quentes: (LeadPrioritario & { marcas: string | null })[]; total_quentes: number; pendencias: string[]; gerado_em: string;
};

export const TEMPERATURA: Record<string, { rotulo: string; classe: string; ponto: string }> = {
  quente: { rotulo: "Quente", classe: "bg-rose-500/12 text-rose-700 dark:text-rose-300", ponto: "bg-rose-500" },
  morno: { rotulo: "Morno", classe: "bg-amber-500/15 text-amber-800 dark:text-amber-300", ponto: "bg-amber-500" },
  em_pesquisa: { rotulo: "Em pesquisa", classe: "bg-slate-500/12 text-slate-700 dark:text-slate-300", ponto: "bg-slate-400" },
};
export const LOCALIZACAO: Record<string, { rotulo: string; dica: string }> = {
  confirmada: { rotulo: "confirmada", dica: "Endereço do CNPJ na Receita Federal ou confirmado por uma pessoa" },
  estimada: { rotulo: "estimada", dica: "UF declarada pelo titular na RPI; ainda sem confirmação cadastral" },
  pendente: { rotulo: "pendente", dica: "Sem UF confirmada nem declarada" },
};
export const ETAPA_STATUS: Record<StatusEtapa, { rotulo: string; classe: string }> = {
  concluida: { rotulo: "Concluída", classe: "bg-emerald-500 text-white" },
  em_execucao: { rotulo: "Em execução", classe: "bg-sky-500 text-white" },
  pendente: { rotulo: "Pendente", classe: "bg-muted text-muted-foreground" },
  erro: { rotulo: "Com erro", classe: "bg-red-500 text-white" },
  sem_dados: { rotulo: "Sem leads", classe: "bg-muted text-muted-foreground" },
};

/** Agente responsável pela fase atual de um estado (pelos números reais da etapa). */
export function responsavel(u: UFSemana): string {
  if (u.falhas) return "Revisão humana";
  if (u.verificados_inpi < u.processos) return "Vítor · verificação no INPI";
  if (u.pesquisados < u.leads) return "Sérgio · pesquisa de contatos";
  if (u.pendencias_validacao) return "Valéria · validação";
  return "Quintino · qualificação";
}

/** Rampa sequencial (azul) para o mapa: 5 degraus, claro → escuro. */
export const RAMPA = ["#cde2fb", "#9ec5f4", "#5598e7", "#256abf", "#104281"];

export function degrau(v: number, max: number): number {
  if (v <= 0 || max <= 0) return -1;
  return Math.min(4, Math.floor((v / max) * 5 - 1e-9));
}
