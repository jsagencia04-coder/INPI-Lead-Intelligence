export type DashboardSummary = {
  leads_whatsapp_validado: number;
  procurador_ausente_confirmado: number;
  custo_ia_semana_usd: number;
  processos_importados: number;
  processos_sem_procurador: number;
  processos_descartados: number;
  leads_encontrados: number;
  contatos_validados: number;
  leads_sem_contato: number;
  pesquisas_pendentes: number;
  agentes_em_execucao: number;
  revisoes_abertas: number;
};

export type Job = {
  id: number;
  tipo: string;
  status: "queued" | "running" | "succeeded" | "failed" | "dead" | "cancelled";
  tentativas: number;
  criado_em: string;
  iniciado_em: string | null;
  finalizado_em: string | null;
  locked_by: string | null;
  ultimo_erro: string | null;
};

export type Edition = {
  numero: number;
  data_publicacao: string | null;
  status: string;
  detectada_em: string;
  processada_em: string | null;
};

export type Process = {
  numero_processo: string;
  marca_nome: string | null;
  apresentacao: string | null;
  natureza: string | null;
  classes_nice: string[];
  situacao_atual: string | null;
  procurador_status: "com_procurador" | "sem_confirmado" | "sem_na_rpi" | "desconhecido";
  procurador_nome: string | null;
  procurador_fonte: string | null;
  descartado: boolean;
  updated_at: string;
};

export type LeadListItem = {
  id: number;
  temperatura?: "quente" | "morno" | "em_pesquisa" | null;
  temperatura_motivos?: string[];
  geo_uf?: string | null;
  geo_municipio?: string | null;
  geo_status?: string;
  titular: string;
  uf: string | null;
  tipo_provavel: string;
  cnpj: string | null;
  cnpj_status: string;
  status: string;
  prioridade: string | null;
  score: number | null;
  segmento: string | null;
  categoria_principal: string | null;
  prazo_ate: string | null;
  procurador_confirmado: boolean;
  precisa_revisao: boolean;
  n_processos: number;
  n_contatos: number;
  n_validados: number;
  whatsapp: string | null;
  whatsapp_status: "confirmado" | "validado" | "candidato" | null;
  servico_principal?: "manifestacao_oposicao" | "recurso_indeferimento" | null;
  classificacao_oposicao?: string | null;
  classificacao_recurso?: string | null;
};

export type Paged<T> = { total: number; items: T[] };

export type RpiFile = {
  id: number;
  formato: string;
  nome_arquivo: string;
  bytes: number;
  sha256: string;
  source_url: string;
  baixado_em: string;
};

export type EditionStats = {
  processos_no_xml?: number;
  processos_importados?: number;
  publicacoes_novas?: number;
  oportunidades_elegiveis?: number;
  oportunidades_descartadas?: number;
  titulares_unicos?: number;
  despachos_novos?: string[];
  elegiveis_por_categoria?: Record<string, number>;
  motivos_descarte?: Record<string, number>;
  escopo?: string;
};

export type RpiEdition = {
  numero: number;
  data_publicacao: string | null;
  status: string;
  detectada_em: string;
  coletada_em: string | null;
  processada_em: string | null;
  observacoes: string | null;
  stats: EditionStats;
  arquivos: RpiFile[];
};

export type DespachoType = {
  codigo: string;
  nome: string;
  categoria_comercial: string;
  ativo_para_leads: boolean;
  revisar: boolean;
  fonte: string | null;
  confirmado_por: string | null;
  confirmado_em: string | null;
  publicacoes: number;
};

export type ProcessRow = Process & {
  titulares: string | null;
  categoria: string | null;
  despacho_codigo: string | null;
  oportunidade_status: "elegivel" | "descartada" | null;
  motivo_descarte: string | null;
  rpi: number | null;
};
