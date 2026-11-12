"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { AlertTriangle, Bell, CheckCircle2, ChevronRight, Info, Menu, Search, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { SEVERIDADE, useAlertas, type Pendencia } from "@/lib/alerts";
import { itemAtual } from "@/lib/nav";

const ICONE: Record<Pendencia["severidade"], typeof Info> = { critico: AlertTriangle, aviso: AlertTriangle, oportunidade: Sparkles, info: Info };

/** Barra superior: onde estou, busca rápida (Ctrl+K) e central de notificações. */
export function Topbar() {
  const pathname = usePathname();
  const alertas = useAlertas();
  const [sino, setSino] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  useEffect(() => setSino(false), [pathname]);
  useEffect(() => {
    if (!sino) return;
    const fora = (e: MouseEvent) => { if (caixa.current && !caixa.current.contains(e.target as Node)) setSino(false); };
    document.addEventListener("mousedown", fora);
    return () => document.removeEventListener("mousedown", fora);
  }, [sino]);
  if (pathname === "/login") return null;
  const atual = itemAtual(pathname);
  const total = alertas?.reduce((n, a) => n + (a.severidade === "info" ? 0 : 1), 0) ?? 0;
  const critico = alertas?.some((a) => a.severidade === "critico");

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border/70 bg-background/80 px-3 backdrop-blur-md md:px-6">
      <button onClick={() => window.dispatchEvent(new Event("inpi:menu"))} className="rounded-lg p-2 hover:bg-accent md:hidden" aria-label="Abrir menu">
        <Menu className="size-5" />
      </button>
      <nav className="hidden min-w-0 items-center gap-1.5 text-sm sm:flex" aria-label="Você está em">
        <span className="text-muted-foreground">{atual?.grupo ?? "INPI Lead Intelligence"}</span>
        {atual && <><ChevronRight className="size-3.5 text-muted-foreground" /><span className="truncate font-medium">{atual.item.label}</span></>}
      </nav>

      <button
        onClick={() => window.dispatchEvent(new Event("inpi:busca"))}
        className="ml-auto flex h-9 w-full max-w-xs items-center gap-2 rounded-lg border bg-card px-3 text-sm text-muted-foreground shadow-xs transition-colors hover:border-ring/60 sm:max-w-sm"
      >
        <Search className="size-4" />
        <span className="flex-1 truncate text-left">Buscar lead, contato ou ação…</span>
        <kbd className="hidden rounded border bg-muted px-1.5 font-mono text-[10px] sm:inline">Ctrl K</kbd>
      </button>

      <div className="relative" ref={caixa}>
        <button onClick={() => setSino(!sino)} className="relative rounded-lg p-2 hover:bg-accent" aria-label={`Notificações: ${total} pendência(s)`} aria-expanded={sino}>
          <Bell className="size-5" />
          {total > 0 && (
            <span className={cn("num absolute -right-0.5 -top-0.5 grid min-w-4 place-items-center rounded-full px-1 text-[10px] font-semibold text-white",
              critico ? "bg-[var(--critical)]" : "bg-primary")}>{total}</span>
          )}
        </button>
        {sino && (
          <div className="entrar absolute right-0 top-11 z-50 w-[22rem] max-w-[calc(100vw-1.5rem)] overflow-hidden rounded-2xl border bg-card shadow-2xl">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <div className="font-semibold">Pendências</div>
              <span className="text-xs text-muted-foreground">atualiza a cada 30 s</span>
            </div>
            {!alertas?.length ? (
              <div className="flex items-center gap-2 px-4 py-6 text-sm text-muted-foreground"><CheckCircle2 className="size-4 text-[var(--success)]" /> Tudo em dia. Nenhuma pendência agora.</div>
            ) : (
              <ul className="max-h-[60vh] divide-y overflow-y-auto">
                {alertas.map((a) => {
                  const s = SEVERIDADE[a.severidade];
                  const I = ICONE[a.severidade];
                  return (
                    <li key={a.chave}>
                      <Link href={a.href} className="flex gap-3 px-4 py-3 hover:bg-accent/50">
                        <span className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg", s.fundo, s.texto)}><I className="size-4" /></span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-2 text-sm font-medium"><span className="num">{a.quantidade.toLocaleString("pt-BR")}</span><span className="truncate">{a.titulo}</span></span>
                          <span className="mt-0.5 block text-xs text-muted-foreground">{a.descricao}</span>
                        </span>
                        <span className={cn("eyebrow mt-1 shrink-0 text-[9px]", s.texto)}>{s.rotulo}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
