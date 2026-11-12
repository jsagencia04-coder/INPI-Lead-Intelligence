"use client";

import Link from "next/link";
import { ArrowUpRight, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Sparkline } from "@/components/charts";
import { TOM, type Tom } from "@/lib/nav";

/** Card de indicador com identidade de cor, ícone, valor principal, contexto e tendência opcional. */
export function KpiCard({ rotulo, valor, icon: Icon, tom, contexto, tendencia, href, destaque }: {
  rotulo: string;
  valor: string;
  icon: LucideIcon;
  tom: Tom;
  contexto?: React.ReactNode;
  tendencia?: number[];
  href?: string;
  destaque?: boolean;
}) {
  const t = TOM[tom];
  const corpo = (
    <div className={cn("surface lift group relative flex h-full flex-col overflow-hidden p-4", destaque && "ring-1 ring-inset ring-primary/20")}>
      <span className={cn("absolute inset-x-0 top-0 h-1 bg-gradient-to-r opacity-90", t.chip)} />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-medium text-muted-foreground">{rotulo}</div>
          <div className="num mt-1.5 text-2xl font-semibold leading-none sm:text-[1.75rem]">{valor}</div>
        </div>
        <span className={cn("hidden size-10 shrink-0 place-items-center min-[420px]:grid rounded-xl bg-gradient-to-br text-white shadow-md", t.chip)}
          style={{ boxShadow: `0 8px 18px -8px ${t.hex}` }}>
          <Icon className="size-5" />
        </span>
      </div>
      {contexto && <div className="mt-2 text-xs text-muted-foreground">{contexto}</div>}
      <div className="-mx-1 mt-auto h-9 pt-2">{tendencia && tendencia.some((v) => v > 0) ? <Sparkline valores={tendencia} cor={t.hex} /> : null}</div>
      {href && <ArrowUpRight className="absolute bottom-3 right-3 size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />}
    </div>
  );
  return href ? <Link href={href} className="block h-full rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{corpo}</Link> : corpo;
}

/** Bloco de seção (título, subtítulo, ação e conteúdo) com o padrão visual da plataforma. */
export function Secao({ titulo, subtitulo, acao, children, className, icon: Icon }: {
  titulo: string; subtitulo?: string; acao?: React.ReactNode; children: React.ReactNode; className?: string; icon?: LucideIcon;
}) {
  return (
    <section className={cn("surface entrar flex min-w-0 flex-col p-5", className)}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {Icon && <span className="grid size-8 place-items-center rounded-lg bg-primary/10 text-primary"><Icon className="size-4" /></span>}
          <div>
            <h2 className="font-semibold leading-tight">{titulo}</h2>
            {subtitulo && <p className="mt-0.5 text-xs text-muted-foreground">{subtitulo}</p>}
          </div>
        </div>
        {acao}
      </div>
      <div className="min-w-0 flex-1">{children}</div>
    </section>
  );
}
