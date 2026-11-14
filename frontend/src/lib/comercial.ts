/** V2.6 · Regras comerciais (espelham backend/app/comercial.py): prioridade do despacho, ordem SC → RS → PR, representação. */

export const PRIORIDADE: Record<number, { rotulo: string; classe: string }> = {
  1: { rotulo: "1 · Oposição apresentada", classe: "bg-rose-500/15 text-rose-700" },
  2: { rotulo: "2 · Indeferimento", classe: "bg-amber-500/15 text-amber-800" },
};

export const UFS_SUL = ["SC", "RS", "PR"] as const;

export const PROCURADOR: Record<string, { rotulo: string; prospecta: boolean }> = {
  SEM_PROCURADOR_CONFIRMADO: { rotulo: "Sem procurador (confirmado)", prospecta: true },
  COM_PROCURADOR: { rotulo: "Com procurador", prospecta: false },
  PROCURADOR_DESCONHECIDO: { rotulo: "Representação desconhecida", prospecta: false },
  ERRO_NA_IDENTIFICACAO: { rotulo: "Erro na identificação", prospecta: false },
};

export type OportunidadeOp = {
  id: number; numero_processo: string; servico: string; prioridade: number; marca_nome: string | null; titular: string;
  geo_uf: string | null; geo_municipio: string | null; rpi_numero: number; data_publicacao: string | null; despacho_codigo: string;
  prazo_fim: string | null; prazo_status: string; procurador_situacao: string; lead_id: number | null; pipeline_stage: string | null;
  no_pipeline: boolean; contatos: number; contatos_validados: number;
};

export type IndicadoresComerciais = {
  edicao_minima: number; rpis_processadas: number;
  edicoes: { numero: number; data_publicacao: string | null; status: string; completa: boolean; alerta: string | null; auditoria: Record<string, unknown> }[];
  oportunidades: { oposicoes: number; indeferimentos: number; titulares: number; no_pipeline: number; com_contato: number };
  representacao: Record<string, number>;
  sul: { uf: string; ordem: number; oposicoes: number; indeferimentos: number; titulares: number; no_pipeline: number; com_contato: number }[];
  sem_uf: { oposicoes: number; indeferimentos: number };
  leads: { leads: number; no_pipeline: number; aguardando_revisao: number; com_contato: number; com_autorizacao: number; elegiveis_primeiro_contato: number; duplicados_mesclados: number };
};
