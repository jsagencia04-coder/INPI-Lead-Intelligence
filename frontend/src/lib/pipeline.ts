/** Etapas do pipeline comercial (mesma ordem do backend) e fases para leitura rápida. */
export const ETAPAS: { id: string; nome: string; fase: string }[] = [
  { id: "lead_novo", nome: "Lead novo", fase: "Identificação" },
  { id: "investigando", nome: "Investigando", fase: "Identificação" },
  { id: "contato_identificado", nome: "Contato identificado", fase: "Identificação" },
  { id: "contato_validado", nome: "Contato validado", fase: "Identificação" },
  { id: "aguardando_autorizacao", nome: "Aguardando autorização", fase: "Elegibilidade" },
  { id: "elegivel_primeiro_contato", nome: "Elegível para primeiro contato", fase: "Elegibilidade" },
  { id: "mensagem_programada", nome: "Mensagem programada", fase: "Primeiro contato" },
  { id: "mensagem_enviada", nome: "Mensagem enviada", fase: "Primeiro contato" },
  { id: "mensagem_entregue", nome: "Mensagem entregue", fase: "Primeiro contato" },
  { id: "resposta_recebida", nome: "Resposta recebida", fase: "Primeiro contato" },
  { id: "interessado", nome: "Interessado", fase: "Negociação" },
  { id: "reuniao", nome: "Reunião", fase: "Negociação" },
  { id: "proposta_enviada", nome: "Proposta enviada", fase: "Negociação" },
  { id: "negociacao", nome: "Negociação", fase: "Negociação" },
  { id: "fechado", nome: "Fechado", fase: "Resultado" },
  { id: "perdido", nome: "Perdido", fase: "Resultado" },
  { id: "opt_out", nome: "Opt-out", fase: "Resultado" },
];
export const FASES = ["Identificação", "Elegibilidade", "Primeiro contato", "Negociação", "Resultado"] as const;

export function porFase(contagem: { chave: string; n: number }[]) {
  const m = Object.fromEntries(contagem.map((c) => [c.chave, c.n]));
  return FASES.map((f) => ({ fase: f, etapas: ETAPAS.filter((e) => e.fase === f).map((e) => ({ ...e, n: m[e.id] ?? 0 })) }))
    .map((g) => ({ ...g, total: g.etapas.reduce((s, e) => s + e.n, 0) }));
}
