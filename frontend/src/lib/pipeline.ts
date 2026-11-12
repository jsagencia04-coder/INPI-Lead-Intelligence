/** Etapas do pipeline comercial (mesma ordem do backend) e fases para leitura rápida. */
export const ETAPAS: { id: string; nome: string; fase: string }[] = [
  { id: "lead_novo", nome: "Lead novo", fase: "Prospecção" },
  { id: "investigando", nome: "Investigando", fase: "Prospecção" },
  { id: "contato_identificado", nome: "Contato identificado", fase: "Prospecção" },
  { id: "contato_validado", nome: "Contato validado", fase: "Prospecção" },
  { id: "aguardando_autorizacao", nome: "Aguardando autorização", fase: "Autorização" },
  { id: "elegivel_primeiro_contato", nome: "Elegível para primeiro contato", fase: "Autorização" },
  { id: "mensagem_programada", nome: "Mensagem programada", fase: "Contato" },
  { id: "mensagem_enviada", nome: "Mensagem enviada", fase: "Contato" },
  { id: "mensagem_entregue", nome: "Mensagem entregue", fase: "Contato" },
  { id: "resposta_recebida", nome: "Resposta recebida", fase: "Contato" },
  { id: "interessado", nome: "Interessado", fase: "Negócio" },
  { id: "reuniao", nome: "Reunião", fase: "Negócio" },
  { id: "proposta_enviada", nome: "Proposta enviada", fase: "Negócio" },
  { id: "negociacao", nome: "Negociação", fase: "Negócio" },
  { id: "fechado", nome: "Fechado", fase: "Resultado" },
  { id: "perdido", nome: "Perdido", fase: "Resultado" },
  { id: "opt_out", nome: "Opt-out", fase: "Resultado" },
];
export const FASES = ["Prospecção", "Autorização", "Contato", "Negócio", "Resultado"] as const;

export function porFase(contagem: { chave: string; n: number }[]) {
  const m = Object.fromEntries(contagem.map((c) => [c.chave, c.n]));
  return FASES.map((f) => ({ fase: f, etapas: ETAPAS.filter((e) => e.fase === f).map((e) => ({ ...e, n: m[e.id] ?? 0 })) }))
    .map((g) => ({ ...g, total: g.etapas.reduce((s, e) => s + e.n, 0) }));
}
