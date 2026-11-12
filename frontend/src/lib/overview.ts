/** Tipos do painel executivo (/api/dashboard/overview). */
import type { Pendencia } from "@/lib/alerts";

export type Contagem = { chave: string; n: number };
export type AgenteStats = { tipo: string; execucoes: number; sucesso: number; falhas: number; duracao_media_s: number | null;
  ultima_execucao: string | null; taxa_sucesso: number | null };
export type Overview = {
  gerado_em: string;
  kpis: {
    processos: number; oportunidades: number; leads: number; leads_7d: number; titulares_com_contato: number; contatos_validados: number;
    whatsapp_total: number; whatsapp_validado: number; autorizacoes: number; enviadas: number; entregues: number; respostas: number;
    contatos_manuais: number; em_negociacao: number; fechados: number; custo_ia_semana: number; executando: number; na_fila: number;
    taxa_conversao: number | null;
  };
  series: { dia: string; leads: number; contatos: number; whatsapp: number; tarefas_ok: number; tarefas_falha: number }[];
  pipeline: Contagem[];
  whatsapp_niveis: Contagem[];
  contatos_tipo: Contagem[];
  categorias: Contagem[];
  prioridades: Contagem[];
  ufs: Contagem[];
  edicoes: { numero: number; data_publicacao: string | null; status: string; processada_em: string | null; processos: string | null }[];
  agentes: Record<string, AgenteStats>;
  pendencias: Pendencia[];
};
