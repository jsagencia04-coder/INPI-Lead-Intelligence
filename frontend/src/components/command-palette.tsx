"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, CornerDownLeft, Download, Search, User, Zap, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, apiDownload } from "@/lib/api";
import { TODOS, TOM } from "@/lib/nav";

type Opcao = { id: string; grupo: string; titulo: string; detalhe?: string; icon: LucideIcon; cor?: string; executar: () => void };

/** Busca e ações rápidas (Ctrl+K / ⌘K): ir para qualquer módulo, abrir um lead ou executar uma tarefa frequente. */
export function CommandPalette() {
  const router = useRouter();
  const [aberto, setAberto] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const [leads, setLeads] = useState<{ id: number; titular: string; uf: string | null; cnpj: string | null }[]>([]);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setAberto((v) => !v); }
      if (e.key === "Escape") setAberto(false);
    };
    const abrir = () => setAberto(true);
    window.addEventListener("keydown", tecla);
    window.addEventListener("inpi:busca", abrir);
    return () => { window.removeEventListener("keydown", tecla); window.removeEventListener("inpi:busca", abrir); };
  }, []);
  useEffect(() => { if (aberto) { setQ(""); setSel(0); setLeads([]); setTimeout(() => input.current?.focus(), 10); } }, [aberto]);
  useEffect(() => {
    if (!aberto || q.trim().length < 2) { setLeads([]); return; }
    const t = setTimeout(() => {
      api<{ items: { id: number; titular: string; uf: string | null; cnpj: string | null }[] }>(`/api/leads?q=${encodeURIComponent(q.trim())}&limit=6`)
        .then((r) => setLeads(r.items)).catch(() => setLeads([]));
    }, 200);
    return () => clearTimeout(t);
  }, [q, aberto]);

  const ir = (href: string) => () => { setAberto(false); router.push(href); };
  const opcoes = useMemo<Opcao[]>(() => {
    const acoes: Opcao[] = [
      { id: "a-resp", grupo: "Ações rápidas", titulo: "Tratar respostas de WhatsApp", icon: Zap, executar: ir("/pipeline?etapa=resposta_recebida") },
      { id: "a-eleg", grupo: "Ações rápidas", titulo: "Leads prontos para o primeiro contato", icon: Zap, executar: ir("/pipeline?etapa=elegivel_primeiro_contato") },
      { id: "a-aprov", grupo: "Ações rápidas", titulo: "Aprovar leads qualificados", icon: Zap, executar: ir("/leads?revisao=true") },
      { id: "a-cand", grupo: "Ações rápidas", titulo: "Confirmar WhatsApp candidatos", icon: Zap, executar: ir("/contatos?filtro=wa_candidato") },
      { id: "a-rev", grupo: "Ações rápidas", titulo: "Resolver revisões abertas", icon: Zap, executar: ir("/revisoes") },
      { id: "a-rpi", grupo: "Ações rápidas", titulo: "Importar uma edição da RPI", icon: Zap, executar: ir("/rpi") },
      { id: "a-exp", grupo: "Ações rápidas", titulo: "Exportar contatos com WhatsApp (Excel)", icon: Download,
        executar: () => { setAberto(false); apiDownload("/api/contact-central/export?formato=xlsx&filtro=whatsapp", "contatos-whatsapp.xlsx"); } },
    ];
    const paginas: Opcao[] = TODOS.map((i) => ({ id: "p" + i.href, grupo: "Módulos", titulo: i.label, detalhe: i.descricao, icon: i.icon, cor: TOM[i.tom].chip, executar: ir(i.href) }));
    const achados: Opcao[] = leads.map((l) => ({ id: "l" + l.id, grupo: "Leads", titulo: l.titular, detalhe: [l.uf, l.cnpj].filter(Boolean).join(" · "), icon: User, executar: ir(`/leads/${l.id}`) }));
    const termo = q.trim().toLowerCase();
    const casa = (o: Opcao) => !termo || `${o.titulo} ${o.detalhe ?? ""}`.toLowerCase().includes(termo);
    return [...achados, ...acoes.filter(casa), ...paginas.filter(casa)];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, leads]);
  useEffect(() => setSel(0), [q, leads.length]);

  if (!aberto) return null;
  const teclado = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, opcoes.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    if (e.key === "Enter" && opcoes[sel]) { e.preventDefault(); opcoes[sel].executar(); }
  };
  let grupoAnterior = "";

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center bg-slate-950/40 p-3 pt-[12vh] backdrop-blur-sm" onClick={() => setAberto(false)}>
      <div className="entrar w-full max-w-xl overflow-hidden rounded-2xl border bg-card shadow-2xl" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Busca e ações rápidas">
        <div className="flex items-center gap-3 border-b px-4">
          <Search className="size-5 text-muted-foreground" />
          <input ref={input} autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={teclado}
            placeholder="Buscar lead por nome ou CNPJ, módulo ou ação…" className="h-14 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground" />
          <kbd className="rounded border bg-muted px-1.5 font-mono text-[10px] text-muted-foreground">Esc</kbd>
        </div>
        <ul className="max-h-[55vh] overflow-y-auto p-2" role="listbox">
          {opcoes.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted-foreground">Nada encontrado.</li>}
          {opcoes.map((o, i) => {
            const cab = o.grupo !== grupoAnterior;
            grupoAnterior = o.grupo;
            return (
              <li key={o.id}>
                {cab && <div className="eyebrow px-3 pb-1 pt-2 text-muted-foreground">{o.grupo}</div>}
                <button onMouseEnter={() => setSel(i)} onClick={o.executar} role="option" aria-selected={i === sel}
                  className={cn("flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm", i === sel && "bg-accent")}>
                  <span className={cn("grid size-8 shrink-0 place-items-center rounded-lg", o.cor ? `bg-gradient-to-br ${o.cor} text-white` : "bg-muted text-muted-foreground")}>
                    <o.icon className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{o.titulo}</span>
                    {o.detalhe && <span className="block truncate text-xs text-muted-foreground">{o.detalhe}</span>}
                  </span>
                  {i === sel ? <CornerDownLeft className="size-4 text-muted-foreground" /> : <ArrowRight className="size-4 text-transparent" />}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
