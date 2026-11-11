/** WhatsApp Business API: tipos e rótulos. */
export type WaStatus = {
  configurado: boolean; envio_ativo: boolean; modo: "real" | "simulacao";
  credenciais: Record<string, boolean>; pendencias_para_envio_real: string[];
  template: { nome: string | null; idioma: string }; numeros_teste: number;
  limites: { por_minuto: number; por_dia: number }; webhook: string;
  enviadas_hoje: number; na_fila: number; recebidas_hoje: number;
};

export type WaMensagem = {
  id: number; direcao: "saida" | "entrada"; modo: "simulacao" | "real"; lead_id: number | null; titular: string | null;
  numero: string; numero_processo: string | null; template_nome: string | null; corpo: string | null;
  status: string; motivo: string | null; criado_em: string;
  aceita_em: string | null; enviada_em: string | null; entregue_em: string | null; lida_em: string | null; falhou_em: string | null;
};

export const WA_STATUS: Record<string, { rotulo: string; cor: string }> = {
  simulada: { rotulo: "simulada (não enviada)", cor: "text-slate-600" },
  na_fila: { rotulo: "na fila", cor: "text-sky-700" },
  aceita: { rotulo: "aceita pela Meta", cor: "text-sky-700" },
  enviada: { rotulo: "enviada", cor: "text-sky-700" },
  entregue: { rotulo: "entregue", cor: "text-emerald-700" },
  lida: { rotulo: "lida", cor: "text-emerald-700" },
  falhou: { rotulo: "falhou", cor: "text-destructive" },
  bloqueada: { rotulo: "bloqueada", cor: "text-amber-700" },
  cancelada: { rotulo: "cancelada", cor: "text-slate-600" },
  recebida: { rotulo: "recebida", cor: "text-emerald-700" },
};

export function fmtHora(v: string | null): string {
  if (!v) return "";
  return new Date(v).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}
