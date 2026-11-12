"use client";
/** Frentes comerciais (V2.4): manifestação à oposição × recurso de indeferimento, com o resumo executivo da SILVANE. */
import Link from "next/link";
import { Crown, Flame, Gavel, Scale } from "lucide-react";
import { useApi } from "@/components/use-api";
import { fmtDay } from "@/lib/format";
import { CLASSE, SERVICO, textoPrazo, type Indicadores, type ResumoExecutivo, type Servico } from "@/lib/servicos";
import { cn } from "@/lib/utils";

const n = (v: number | null | undefined) => Number(v ?? 0).toLocaleString("pt-BR");

const LINHAS: [keyof Indicadores, string, string][] = [
  ["identificadas", "Identificadas", "oposições sofridas / indeferimentos"],
  ["titulares", "Titulares afetados", ""],
  ["qualificados", "Leads qualificados", "quentes + mornos"],
  ["contatos_encontrados", "Contatos encontrados", "titulares com contato"],
  ["abertas", "Potencialmente cabíveis", "prazo aberto, sem medida"],
  ["abordados", "Já abordados", "titulares no funil"],
];

function Coluna({ s, ind, escuro }: { s: Servico; ind?: Indicadores; escuro: boolean }) {
  const d = SERVICO[s];
  const Icone = s === "manifestacao_oposicao" ? Scale : Gavel;
  return (
    <Link href={`/oportunidades?servico=${s}`} className={cn("block rounded-xl border p-3 transition-colors", escuro ? "border-white/10 bg-white/[0.04] hover:bg-white/[0.07]" : "bg-card hover:bg-accent/40")}>
      <div className="mb-2 flex items-center gap-2">
        <span className="grid size-7 place-items-center rounded-lg text-white" style={{ background: d.hex }}><Icone className="size-4" /></span>
        <div className="min-w-0">
          <div className={cn("text-sm font-semibold leading-tight", escuro && "text-white")}>{d.rotulo}</div>
          <div className={cn("text-[11px]", escuro ? "text-slate-400" : "text-muted-foreground")}>{d.oferta}</div>
        </div>
        <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-xs font-semibold text-rose-600"><Flame className="size-3" />{n(ind?.quentes)}</span>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-3">
        {LINHAS.map(([k, rot, dica]) => (
          <div key={k} title={dica || undefined}>
            <dt className={cn("truncate text-[11px]", escuro ? "text-slate-400" : "text-muted-foreground")}>{rot}</dt>
            <dd className={cn("num text-lg font-semibold leading-tight", escuro && "text-white")}>{ind ? n(ind[k] as number) : "–"}</dd>
          </div>
        ))}
      </dl>
      {ind?.proximo_vencimento && <div className={cn("mt-2 text-[11px]", escuro ? "text-amber-300" : "text-amber-700")}>Próximo vencimento estimado: {fmtDay(ind.proximo_vencimento)}{ind.proximos_fim ? ` · ${n(ind.proximos_fim)} em até 15 dias` : ""}</div>}
    </Link>
  );
}

export function ServicosResumo({ escuro = false, compacto = false }: { escuro?: boolean; compacto?: boolean }) {
  const { data } = useApi<ResumoExecutivo>("/api/servicos/resumo-executivo", 60000);
  const sub = escuro ? "text-slate-400" : "text-muted-foreground";
  if (!data) return <div className={cn("h-40 animate-pulse rounded-xl", escuro ? "bg-white/5" : "bg-muted")} />;
  const ind = data.indicadores;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Coluna s="manifestacao_oposicao" ind={ind.manifestacao_oposicao} escuro={escuro} />
        <Coluna s="recurso_indeferimento" ind={ind.recurso_indeferimento} escuro={escuro} />
      </div>
      <div className={cn("flex items-start gap-2 rounded-xl border px-3 py-2 text-sm", escuro ? "border-[#e2c27c]/30 bg-[#e2c27c]/[0.06] text-slate-200" : "border-amber-500/30 bg-amber-500/[0.06]")}>
        <Crown className="mt-0.5 size-4 shrink-0 text-amber-500" />
        <p><b>Consolidado da diretoria:</b> {n(ind.consolidado.quentes)} quente(s), {n(ind.consolidado.abertas)} com prazo aberto, {n(ind.consolidado.titulares)} titular(es) somando as duas frentes. {data.texto}</p>
      </div>
      {!compacto && data.melhores.length > 0 && (
        <div>
          <div className={cn("mb-1.5 text-xs font-semibold", sub)}>Melhores oportunidades agora</div>
          <ul className={cn("divide-y rounded-xl border", escuro ? "divide-white/10 border-white/10" : "")}>
            {data.melhores.slice(0, 6).map((o) => (
              <li key={o.id}>
                <Link href={o.lead_id ? `/leads/${o.lead_id}` : `/oportunidades?servico=${o.servico}`} className={cn("flex items-center gap-3 px-3 py-2 text-sm", escuro ? "hover:bg-white/[0.04]" : "hover:bg-accent/40")}>
                  <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", o.classificacao ? CLASSE[o.classificacao].classe : "")}>{o.classificacao ? CLASSE[o.classificacao].rotulo : ""}</span>
                  <span className="min-w-0 flex-1">
                    <span className={cn("block truncate font-medium", escuro && "text-white")}>{o.titular}</span>
                    <span className={cn("block truncate text-[11px]", sub)}>{SERVICO[o.servico].curto} · {o.numero_processo}{o.marca_nome ? ` · ${o.marca_nome}` : ""} · {o.geo_uf ?? "UF ?"}</span>
                  </span>
                  <span className={cn("num shrink-0 text-xs", sub)}>{textoPrazo(o)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
