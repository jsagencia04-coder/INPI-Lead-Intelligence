"use client";
/** Resumo da operação semanal da RPI (painel executivo e Central de Operações da SILVANE). */
import Link from "next/link";
import { Check, Clock, Crown, Flame, Loader2, Radar, X } from "lucide-react";
import { useApi } from "@/components/use-api";
import { fmtDate, fmtDay } from "@/lib/format";
import { ETAPA_STATUS, type Relatorio, type Semana, type StatusEtapa } from "@/lib/territorio";
import { cn } from "@/lib/utils";

const ICONE: Record<StatusEtapa, typeof Check> = { concluida: Check, em_execucao: Loader2, pendente: Clock, erro: X, sem_dados: Clock };

export function OperacaoSemanal({ escuro = false }: { escuro?: boolean }) {
  const { data } = useApi<Semana>("/api/rpi-semana", 30000);
  const { data: sc } = useApi<Relatorio>("/api/rpi-semana/relatorio?uf=SC", 30000);
  const st = data?.status;
  const sub = escuro ? "text-slate-400" : "text-muted-foreground";
  if (data && !st) return <p className={cn("text-sm", sub)}>Nenhuma RPI detectada ainda. A verificação é automática, mesmo com o navegador fechado.</p>;
  if (!st) return <div className={cn("h-28 animate-pulse rounded-xl", escuro ? "bg-white/5" : "bg-muted")} />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold", escuro ? "bg-white/10 text-white" : "bg-primary/10 text-primary")}>
          <Radar className="size-3.5" />RPI nº {st.edicao.numero} · {fmtDay(st.edicao.data_publicacao)}
        </span>
        <span className={cn("text-xs", sub)}>detectada {fmtDate(st.edicao.detectada_em)}</span>
        {st.atraso && <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-700">RPI da semana atrasada</span>}
      </div>
      <ol className="flex items-center gap-1 overflow-x-auto pb-1">
        {st.etapas.map((e, i) => {
          const I = ICONE[e.status];
          return (
            <li key={e.chave} className="flex shrink-0 items-center gap-1">
              <span className={cn("flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium", ETAPA_STATUS[e.status].classe)} title={ETAPA_STATUS[e.status].rotulo}>
                <I className={cn("size-3", e.status === "em_execucao" && "animate-spin")} />{e.nome === "Demais estados" ? "Demais" : e.nome}
              </span>
              {i < st.etapas.length - 1 && <span className={cn("h-px w-3", escuro ? "bg-white/20" : "bg-border")} />}
            </li>
          );
        })}
      </ol>
      {sc && (
        <div className={cn("grid grid-cols-2 gap-2 sm:grid-cols-4", escuro && "text-white")}>
          {([["Manifestações SC", sc.servicos?.manifestacoes_cabiveis ?? sc.oposicoes], ["Recursos SC", sc.servicos?.recursos_cabiveis ?? 0],
            ["Contatos validados", sc.contatos_validados], ["Quentes SC", sc.total_quentes]] as const).map(([k, v]) => (
            <div key={k} className={cn("rounded-xl border px-3 py-2", escuro ? "border-white/10 bg-white/[0.04]" : "bg-card")}>
              <div className={cn("text-[11px]", sub)}>{k}</div><div className="num text-lg font-semibold">{Number(v).toLocaleString("pt-BR")}</div>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3 text-xs">
        {st.trabalhando_em && <span className={cn("inline-flex items-center gap-1", sub)}><Crown className="size-3.5 text-amber-500" />SILVANE trabalhando em <b className={escuro ? "text-white" : "text-foreground"}>{st.trabalhando_em}</b></span>}
        {st.operacao?.sc_primeiros_quentes_em && <span className="inline-flex items-center gap-1 text-rose-600"><Flame className="size-3.5" />SC pronto às {new Date(st.operacao.sc_primeiros_quentes_em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</span>}
        <Link href="/rpi-semanal" className={cn("ml-auto font-medium hover:underline", escuro ? "text-[#e2c27c]" : "text-primary")}>Relatório de SC e Central RPI →</Link>
      </div>
    </div>
  );
}
