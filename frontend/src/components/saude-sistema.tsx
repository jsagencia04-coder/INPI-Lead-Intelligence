"use client";

import { AlertTriangle, CheckCircle2, ServerCog, XCircle } from "lucide-react";
import { useApi } from "@/components/use-api";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";

/** V2.13 · TI (Julio): resultado da última verificação de saúde do sistema (a cada 5 min, 24 h). */
type Check = { nome: string; status: "ok" | "atencao" | "falha"; detalhe: string };
type Saude = {
  ultima: { status: Check["status"]; checks: Check[]; acoes: { acao: string; quantidade: number }[]; criado_em: string } | null;
  ultimas_24h: Record<string, number>;
  eventos: { tipo: string; descricao: string; criado_em: string }[];
};
const NOME: Record<string, string> = {
  banco: "Banco de dados", agendador: "Agendador", tarefas_travadas: "Tarefas travadas", falhas_24h: "Falhas (24 h)",
  fila: "Fila", importacao: "Última importação", rpi_semana: "Revista da semana", whatsapp: "WhatsApp", disco: "Disco",
};
const ICONE = { ok: CheckCircle2, atencao: AlertTriangle, falha: XCircle };
const COR = { ok: "text-emerald-600", atencao: "text-amber-600", falha: "text-red-600" };
const GERAL = { ok: ["Operando normalmente", "bg-emerald-50 text-emerald-800 border-emerald-200"],
  atencao: ["Atenção", "bg-amber-50 text-amber-900 border-amber-200"], falha: ["Falha", "bg-red-50 text-red-800 border-red-200"] } as const;

export function SaudeSistema() {
  const { data: d } = useApi<Saude>("/api/sistema/saude", 30000);
  if (!d) return null;
  const u = d.ultima;
  return (
    <div className="surface mb-4 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <ServerCog className="size-4 text-teal-700" />
        <span className="text-sm font-semibold">Saúde do sistema · TI (Julio)</span>
        {u && <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", GERAL[u.status][1])}>{GERAL[u.status][0]}</span>}
        <span className="ml-auto text-xs text-muted-foreground">
          {u ? `Última verificação ${fmtDate(u.criado_em)} · a cada 5 min, 24 h` : "Primeira verificação em até 5 min"}
          {Object.keys(d.ultimas_24h).length > 0 && ` · 24 h: ${Object.entries(d.ultimas_24h).map(([k, v]) => `${v} ${k}`).join(", ")}`}
        </span>
      </div>
      {u && (
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {u.checks.map((c) => {
            const I = ICONE[c.status];
            return (
              <li key={c.nome} className="flex gap-2 rounded-lg border p-2 text-xs">
                <I className={cn("mt-0.5 size-4 shrink-0", COR[c.status])} />
                <span><span className="block font-medium">{NOME[c.nome] ?? c.nome}</span><span className="text-muted-foreground">{c.detalhe}</span></span>
              </li>
            );
          })}
        </ul>
      )}
      {u && u.acoes.length > 0 && (
        <p className="mt-2 text-xs text-teal-800">Correção automática: {u.acoes.map((a) => `${a.quantidade} tarefa(s) travada(s) devolvida(s) à fila`).join("; ")}</p>
      )}
      {d.eventos.length > 0 && (
        <details className="mt-2 text-xs"><summary className="cursor-pointer text-muted-foreground">Histórico de alertas da TI</summary>
          <ul className="mt-1 space-y-0.5">{d.eventos.map((e, i) => <li key={i}>{fmtDate(e.criado_em)} · {e.descricao}</li>)}</ul>
        </details>
      )}
    </div>
  );
}
