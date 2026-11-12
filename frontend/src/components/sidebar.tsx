"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { LogOut, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { AMBIENTE, PAPEL, sair, type Eu } from "@/lib/auth";
import { api } from "@/lib/api";
import { useAlertas } from "@/lib/alerts";
import { NAV, TOM, itemAtual } from "@/lib/nav";

/** Menu lateral: módulos agrupados por área, com contadores de pendências. */
export function Sidebar() {
  const pathname = usePathname();
  const [aberto, setAberto] = useState(false);
  const [eu, setEu] = useState<Eu | null>(null);
  const alertas = useAlertas();
  useEffect(() => setAberto(false), [pathname]); // fecha o menu do celular ao navegar
  useEffect(() => {
    const abrir = () => setAberto(true);
    window.addEventListener("inpi:menu", abrir);
    return () => window.removeEventListener("inpi:menu", abrir);
  }, []);
  useEffect(() => {
    if (pathname === "/login") return;
    api<Eu>("/api/auth/me").then(setEu).catch(() => setEu(null));
  }, [pathname]);
  if (pathname === "/login") return null;
  const atual = itemAtual(pathname)?.item.href;
  const contar = (chaves?: string[]) =>
    (chaves ?? []).reduce((n, k) => n + (alertas?.find((a) => a.chave === k)?.quantidade ?? 0), 0);
  const critico = (chaves?: string[]) => (chaves ?? []).some((k) => alertas?.find((a) => a.chave === k)?.severidade === "critico");

  return (
    <>
      {aberto && <div className="fixed inset-0 z-40 bg-slate-950/50 backdrop-blur-sm md:hidden" onClick={() => setAberto(false)} />}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-72 shrink-0 flex-col text-slate-300 transition-transform md:sticky md:top-0 md:z-auto md:h-dvh md:w-64 md:translate-x-0",
          "bg-[radial-gradient(120%_60%_at_0%_0%,var(--sidebar-2),var(--sidebar)_60%)] shadow-2xl md:shadow-none",
          aberto ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center gap-3 px-5 pb-4 pt-5">
          <div className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-indigo-400 via-violet-500 to-fuchsia-500 shadow-lg shadow-violet-900/40">
            <Sparkles className="size-5 text-white" />
          </div>
          <div className="min-w-0 flex-1 leading-tight">
            <div className="truncate text-sm font-semibold text-white">INPI Lead Intelligence</div>
            <div className="text-[11px] text-slate-400">Inteligência comercial com IA</div>
          </div>
          <button onClick={() => setAberto(false)} className="rounded p-1 hover:bg-white/10 md:hidden" aria-label="Fechar menu"><X className="size-4" /></button>
        </div>

        <nav className="scroll-thin flex-1 space-y-5 overflow-y-auto px-3 pb-4" aria-label="Módulos">
          {NAV.map((g) => {
            const itens = g.itens.filter((i) => !i.admin || eu?.papel === "admin");
            if (!itens.length) return null;
            return (
              <div key={g.titulo}>
                <div className="eyebrow mb-1.5 px-3 text-slate-500">{g.titulo}</div>
                <ul className="space-y-0.5">
                  {itens.map((i) => {
                    const ativo = atual === i.href;
                    const n = contar(i.alerta);
                    return (
                      <li key={i.href}>
                        <Link
                          href={i.href}
                          title={i.descricao}
                          className={cn(
                            "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] transition-colors",
                            ativo ? "bg-white/10 font-medium text-white" : "hover:bg-white/[0.06] hover:text-white",
                          )}
                        >
                          {ativo && <span className="absolute inset-y-1.5 left-0 w-[3px] rounded-r-full bg-gradient-to-b from-indigo-300 to-fuchsia-400" />}
                          <span className={cn("grid size-7 place-items-center rounded-md transition-colors",
                            ativo ? `bg-gradient-to-br ${TOM[i.tom].chip} text-white shadow-md` : "bg-white/[0.06] text-slate-400 group-hover:text-white")}>
                            <i.icon className="size-4" />
                          </span>
                          <span className="min-w-0 flex-1 truncate">{i.label}</span>
                          {n > 0 && (
                            <span className={cn("num rounded-full px-1.5 py-px text-[10px] font-semibold",
                              critico(i.alerta) ? "bg-red-500 text-white" : "bg-white/15 text-slate-100")}>
                              {n > 999 ? "999+" : n}
                            </span>
                          )}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </nav>

        {eu && (
          <div className="m-3 rounded-xl border border-white/10 bg-white/[0.04] p-3 text-xs">
            <div className="flex items-center gap-2">
              <div className="grid size-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-sm font-semibold uppercase text-white">
                {(eu.email ?? "?").slice(0, 1)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-slate-100" title={eu.email ?? ""}>{eu.modo === "dev" ? "Modo demonstração" : eu.email}</div>
                <div className="text-slate-400">{eu.modo === "dev" ? "sem login" : PAPEL[eu.papel]}</div>
              </div>
              {eu.modo !== "dev" && (
                <button onClick={sair} className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-white" aria-label="Sair" title="Sair">
                  <LogOut className="size-4" />
                </button>
              )}
            </div>
            <div className={cn("mt-2 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
              eu.ambiente === "producao" ? "bg-emerald-500/15 text-emerald-300" : eu.ambiente === "homologacao" ? "bg-sky-500/15 text-sky-300" : "bg-amber-500/15 text-amber-300")}>
              <span className="size-1.5 rounded-full bg-current" />{AMBIENTE[eu.ambiente] ?? eu.ambiente}
            </div>
            {eu.modo === "dev" && <p className="mt-1.5 text-amber-300/90">Sem login: qualquer pessoa com acesso a este endereço opera o sistema.</p>}
          </div>
        )}
      </aside>
    </>
  );
}
