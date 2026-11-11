"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Activity, BarChart3, BookOpen, Building2, ClipboardCheck, FileText, LayoutDashboard, ListChecks, LogOut, Menu, Contact, ShieldCheck, MessageCircle, Settings2, Users, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { AMBIENTE, PAPEL, sair, type Eu } from "@/lib/auth";
import { api } from "@/lib/api";

const items = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/escritorio", label: "Escritório (AI Office)", icon: Building2 },
  { href: "/rpi", label: "Edições da RPI", icon: BookOpen },
  { href: "/processos", label: "Processos", icon: FileText },
  { href: "/leads", label: "Leads", icon: Users },
  { href: "/contatos", label: "Central de contatos", icon: Contact },
  { href: "/whatsapp", label: "WhatsApp Business", icon: MessageCircle },
  { href: "/revisoes", label: "Revisões", icon: ClipboardCheck },
  { href: "/relatorios", label: "Relatórios", icon: BarChart3 },
  { href: "/jobs", label: "Agentes e jobs", icon: Activity },
  { href: "/operacao", label: "Operação", icon: Settings2 },
  { href: "/despachos", label: "Despachos", icon: ListChecks },
];

export function Sidebar() {
  const pathname = usePathname();
  const [aberto, setAberto] = useState(false);
  useEffect(() => setAberto(false), [pathname]); // fecha o menu do celular ao navegar
  const [eu, setEu] = useState<Eu | null>(null);
  useEffect(() => {
    if (pathname === "/login") return;
    api<Eu>("/api/auth/me").then(setEu).catch(() => setEu(null));
  }, [pathname]);
  if (pathname === "/login") return null;
  return (
    <>
      {/* celular: barra superior com botão de menu */}
      <div className="fixed inset-x-0 top-0 z-40 flex h-12 items-center gap-2 border-b bg-background px-3 md:hidden">
        <button onClick={() => setAberto(true)} className="rounded-md p-2 hover:bg-accent" aria-label="Abrir menu"><Menu className="size-5" /></button>
        <span className="text-sm font-semibold">INPI Lead Intelligence</span>
      </div>
      {aberto && <div className="fixed inset-0 z-40 bg-black/30 md:hidden" onClick={() => setAberto(false)} />}
    <aside className={cn(
      "fixed inset-y-0 left-0 z-50 w-64 shrink-0 border-r bg-background p-4 flex flex-col gap-1 transition-transform md:static md:z-auto md:w-56 md:translate-x-0 md:bg-muted/30",
      aberto ? "translate-x-0" : "-translate-x-full")}>
      <div className="mb-4 flex items-start justify-between px-2">
        <div>
          <div className="text-sm font-semibold">INPI Lead Intelligence</div>
          <div className="text-xs text-muted-foreground">v1.0</div>
        </div>
        <button onClick={() => setAberto(false)} className="rounded p-1 hover:bg-accent md:hidden" aria-label="Fechar menu"><X className="size-4" /></button>
      </div>
      {items.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent",
              active && "bg-accent font-medium",
            )}
          >
            <Icon className="size-4" /> {label}
          </Link>
        );
      })}
      {eu?.papel === "admin" && (
        <Link href="/usuarios" className={cn("flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent", pathname.startsWith("/usuarios") && "bg-accent font-medium")}>
          <ShieldCheck className="size-4" /> Usuários
        </Link>
      )}
      {eu && (
        <div className="mt-auto space-y-1 px-2 pt-3 text-xs text-muted-foreground">
          <div className={cn("inline-block rounded px-1.5 py-0.5 font-medium", eu.ambiente === "producao" ? "bg-emerald-100 text-emerald-900" : eu.ambiente === "homologacao" ? "bg-sky-100 text-sky-900" : "bg-amber-100 text-amber-900")}>
            {AMBIENTE[eu.ambiente] ?? eu.ambiente}
          </div>
          {eu.modo === "dev"
            ? <div className="text-amber-800">Sem login: qualquer pessoa com acesso a este endereço opera o sistema.</div>
            : <div className="truncate" title={eu.email ?? ""}>{eu.email} · {PAPEL[eu.papel]}</div>}
          {eu.modo !== "dev" && (
            <button onClick={sair} className="flex items-center gap-2 rounded-md py-1.5 text-sm hover:text-foreground">
              <LogOut className="size-4" /> Sair
            </button>
          )}
        </div>
      )}
    </aside>
    </>
  );
}
