"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Maximize2, Minus, Plus, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SPRITE_H, SPRITE_W } from "@/office/components/agent-sprite";
import { OfficeScene, type OfficeSceneHandle } from "@/office/components/office-scene";
import { AGENTES, DEPARTAMENTOS, ESTADOS } from "@/office/config";
import { DEPT_ESTADO_COR } from "@/office/demo";
import { agentOfEvent, type OfficeEvent, type OfficeState } from "@/office/real";
import type { Agent, AgentStatus, DeptStatus } from "@/office/types";
import { useDemoOffice } from "@/office/use-demo";
import { useRealOffice, type Conexao } from "@/office/use-real";
import { api } from "@/lib/api";
import "@/office/office.css";

type Sel = { tipo: "agente" | "dept"; id: string } | null;
type Modo = "real" | "demo";

function Avatar({ agent, size = 44 }: { agent: Agent; size?: number }) {
  const v = agent.visual;
  return (
    <svg width={size} height={size} viewBox={`${-4} ${-2} ${SPRITE_W + 8} ${SPRITE_H + 4}`} className="shrink-0 rounded-md bg-muted">
      <use href="#office-pessoa" style={{ ["--cabelo" as string]: v.cabelo, ["--pele" as string]: v.pele,
        ["--camisa" as string]: v.camisa, ["--calca" as string]: v.calca, ["--destaque" as string]: v.destaque }} />
    </svg>
  );
}

function EstadoBadge({ status }: { status: AgentStatus }) {
  const e = ESTADOS[status.state];
  return <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border px-2 py-0.5 text-xs font-medium">
    <span className="size-2 rounded-full" style={{ background: e.cor }} />{e.rotulo}</span>;
}

function desde(ms: number) {
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 60) return `há ${s}s`;
  if (s < 3600) return `há ${Math.round(s / 60)} min`;
  if (s < 86400) return `há ${Math.round(s / 3600)} h`;
  return new Date(ms).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

const hora = (iso: string) => new Date(iso).toLocaleTimeString("pt-BR");

function resumo(r: unknown): string {
  if (!r || typeof r !== "object") return "";
  const o = r as Record<string, unknown>;
  if (typeof o.erro === "string") return o.erro;
  return Object.entries(o).filter(([, v]) => v !== null && typeof v !== "object").slice(0, 3)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(" · ");
}

function linkRef(ref: string | null): string | null {
  if (!ref) return null;
  const [t, v] = ref.split(":");
  return t === "lead" && v !== "?" ? `/leads/${v}` : t === "rpi" ? "/rpi" : t === "processo" ? `/processos?q=${v}` : t === "job" ? "/jobs" : null;
}

const CONEXAO: Record<Conexao, { texto: string; classe: string }> = {
  "tempo-real": { texto: "● Ao vivo · dados reais em tempo real (WebSocket)", classe: "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" },
  consulta: { texto: "Dados reais · WebSocket indisponível, reconectando; atualizando a cada 3 s", classe: "border-amber-500/30 bg-amber-500/10 text-amber-300" },
  conectando: { texto: "Conectando aos agentes…", classe: "border-white/10 bg-white/5 text-slate-300" },
  offline: { texto: "Sem conexão com a API. No Docker: docker compose -f docker-compose.prod.yml logs api", classe: "border-red-500/30 bg-red-500/10 text-red-300" },
};

function Kpis({ st, statuses }: { st: OfficeState; statuses: Record<string, AgentStatus> }) {
  const lista = Object.values(statuses);
  const itens: [string, string, string?][] = [
    ["Agentes", String(AGENTES.length)],
    ["Ativos", String(lista.filter((s) => s.state !== "idle").length)],
    ["Trabalhando", String(lista.filter((s) => s.state === "working" || s.state === "thinking").length)],
    ["Tarefas pendentes", st.kpis.pendentes.toLocaleString("pt-BR")],
    ["Concluídas hoje", st.kpis.concluidas_hoje.toLocaleString("pt-BR"), st.kpis.falhas_hoje ? `${st.kpis.falhas_hoje} falha(s)` : undefined],
    ["Leads", st.kpis.leads.toLocaleString("pt-BR")],
    ["WhatsApp validado", (st.kpis.leads_whatsapp ?? 0).toLocaleString("pt-BR")],
    ["Tokens (semana)", Number(st.kpis.tokens_semana).toLocaleString("pt-BR"), `US$ ${Number(st.kpis.custo_semana_usd).toFixed(2)}`],
  ];
  return (
    <div className="flex gap-2 overflow-x-auto border-b border-white/10 px-4 py-2 md:px-6">
      {itens.map(([k, v, sub]) => (
        <div key={k} className="shrink-0 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5">
          <div className="text-[11px] text-muted-foreground">{k}</div>
          <div className="text-sm font-semibold tabular-nums">{v}{sub && <span className="ml-1.5 text-[11px] font-normal text-muted-foreground">{sub}</span>}</div>
        </div>
      ))}
      <div className={`shrink-0 rounded-lg border px-3 py-1.5 ${st.sistema.worker_ok ? "border-white/10 bg-white/[0.03]" : "border-red-500/40 bg-red-500/10"}`}>
        <div className="text-[11px] text-muted-foreground">Sistema</div>
        <div className="flex items-center gap-1.5 text-sm font-semibold">
          <span className={`size-2 rounded-full ${st.sistema.worker_ok ? "bg-emerald-500" : "bg-red-500"}`} />
          {st.sistema.worker_ok ? "Operando" : "Worker parado"}
        </div>
      </div>
    </div>
  );
}

function Feed({ eventos, aberto, setAberto }: { eventos: OfficeEvent[]; aberto: boolean; setAberto: (v: boolean) => void }) {
  const ordem = [...eventos].reverse().slice(0, 100);
  return (
    <section className="border-t border-white/10 bg-[#0d121c]">
      <button className="flex w-full items-center justify-between px-4 py-1.5 text-xs font-medium md:px-6" onClick={() => setAberto(!aberto)}>
        <span>Atividades em tempo real {eventos.length > 0 && <span className="text-muted-foreground">({eventos.length})</span>}</span>
        {aberto ? <ChevronDown className="size-4" /> : <ChevronUp className="size-4" />}
      </button>
      {aberto && (
        <ol className="h-40 overflow-y-auto border-t border-white/10 px-4 py-1 font-mono text-[11px] md:px-6" aria-live="polite">
          {ordem.length === 0 && <li className="py-2 text-muted-foreground">Nenhum evento ainda. Os eventos aparecem quando os agentes trabalham.</li>}
          {ordem.map((e) => {
            const ag = agentOfEvent(e);
            const dep = DEPARTAMENTOS.find((d) => d.id === ag?.departamento);
            const href = linkRef(e.referencia);
            const falha = e.tipo === "task.failed" || e.tipo === "agent.error";
            return (
              <li key={e.id} className="flex gap-2 border-b border-dashed border-white/10 py-1 last:border-0">
                <span className="shrink-0 text-muted-foreground">{hora(e.criado_em)}</span>
                <span className="shrink-0 font-semibold" style={{ color: dep ? `color-mix(in srgb, ${dep.cor} 55%, white)` : "#94a3b8" }}>[{(dep?.nome ?? "SISTEMA").toUpperCase()}]</span>
                <span className="shrink-0 text-muted-foreground">{ag?.nome ?? e.agente}</span>
                <span className={`shrink-0 ${falha ? "text-red-400" : "text-slate-500"}`}>{e.tipo}</span>
                <span className={`min-w-0 truncate ${falha ? "text-red-300" : "text-slate-200"}`} title={`${e.descricao} ${resumo(e.resultado)}`}>
                  {e.descricao}{resumo(e.resultado) && <span className="text-muted-foreground"> · {resumo(e.resultado)}</span>}
                </span>
                {href ? <Link href={href} className="ml-auto shrink-0 text-[#e2c27c] underline">{e.referencia}</Link>
                  : <span className="ml-auto shrink-0 text-muted-foreground">{e.referencia}</span>}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function HistoricoAgente({ agent }: { agent: Agent }) {
  const [h, setH] = useState<any[] | null>(null);
  useEffect(() => {
    let vivo = true;
    const tipos = agent.jobTypes.filter((t) => t !== "scheduler").join(",");
    if (!tipos) { setH([]); return; }
    const load = () => api<any[]>(`/api/office/history?tipos=${tipos}&limit=8`).then((r) => vivo && setH(r)).catch(() => vivo && setH([]));
    load();
    const t = setInterval(load, 5000);
    return () => { vivo = false; clearInterval(t); };
  }, [agent]);
  if (!h) return <p className="text-xs text-muted-foreground">Carregando histórico…</p>;
  if (!h.length) return <p className="text-xs text-muted-foreground">Nenhuma execução registrada ainda.</p>;
  const ult = h.find((j) => j.status === "succeeded" || j.status === "dead");
  return (
    <div className="space-y-2">
      {ult && (
        <div className="rounded-md bg-white/5 p-2 text-xs">
          <div className="font-medium">Resultado da última execução ({ult.status === "dead" ? "falhou" : "concluída"})</div>
          <div className="mt-0.5 break-words text-muted-foreground">{ult.erro || resumo(ult.resultado) || "sem detalhes"}</div>
        </div>
      )}
      <ul className="space-y-1 text-xs">
        {h.map((j) => (
          <li key={j.id} className="flex items-center gap-2">
            <span className="size-2 shrink-0 rounded-full" style={{ background: j.status === "succeeded" ? "#10b981" : j.status === "dead" ? "#ef4444" : j.status === "running" ? "#22c55e" : "#f59e0b" }} />
            <span className="min-w-0 flex-1 truncate" title={j.tarefa}>{j.tarefa}</span>
            <span className="shrink-0 text-muted-foreground">{desde(Date.parse(j.finalizado_em ?? j.iniciado_em ?? j.criado_em))}</span>
          </li>
        ))}
      </ul>
      <Link href={`/jobs?tipo=${agent.jobTypes[0]}`} className="text-xs text-[#e2c27c] underline">Ver todos os jobs</Link>
    </div>
  );
}

export default function EscritorioPage() {
  const [modo, setModo] = useState<Modo>("real");
  const demo = useDemoOffice();
  const real = useRealOffice(modo === "real");
  const [sel, setSel] = useState<Sel>(null);
  const [feedAberto, setFeedAberto] = useState(true);
  const cena = useRef<OfficeSceneHandle>(null);

  const vazio = Object.fromEntries(AGENTES.map((a) => [a.id, { state: "idle", tarefa: null, desde: Date.now(), fonte: "real" } as AgentStatus]));
  const deptVazio = Object.fromEntries(DEPARTAMENTOS.map((d) => [d.id, { estado: "Disponível", tarefas: 0, ativos: 0 } as DeptStatus]));
  const statuses = modo === "demo" ? demo.statuses : real.statuses ?? vazio;
  const depts = modo === "demo" ? demo.depts : real.depts ?? deptVazio;
  const pausado = demo.pausado;

  const agente = sel?.tipo === "agente" ? AGENTES.find((a) => a.id === sel.id) : null;
  const dept = sel?.tipo === "dept" ? DEPARTAMENTOS.find((d) => d.id === sel.id)
    : agente ? DEPARTAMENTOS.find((d) => d.id === agente.departamento) : null;
  const selo = modo === "demo"
    ? <Badge variant="outline" className="border-amber-500/50 text-amber-300">dados de demonstração</Badge>
    : <Badge variant="outline" className="border-emerald-500/50 text-emerald-300">dados reais</Badge>;

  return (
    <div className="dark -m-4 -mt-4 flex h-[calc(100dvh-3rem)] flex-col bg-[#0b0f17] text-foreground md:-m-6 md:h-[100dvh]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-gradient-to-r from-[#111827] to-[#0b0f17] px-4 py-3 md:px-6">
        <div>
          <h1 className="text-xl font-semibold tracking-[0.08em]"><span className="bg-gradient-to-r from-[#f0d9a3] to-[#c9a45c] bg-clip-text text-transparent">INPI AI OFFICE</span></h1>
          <p className="hidden text-xs text-muted-foreground sm:block">Escritório virtual dos agentes de prospecção</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border p-0.5 text-xs" role="radiogroup" aria-label="Fonte dos dados">
            <button role="radio" aria-checked={modo === "real"} onClick={() => setModo("real")}
              className={`rounded px-2.5 py-1 ${modo === "real" ? "bg-emerald-500/20 font-medium text-emerald-300" : "text-muted-foreground hover:bg-accent"}`}>
              Dados reais</button>
            <button role="radio" aria-checked={modo === "demo"} onClick={() => setModo("demo")}
              className={`rounded px-2.5 py-1 ${modo === "demo" ? "bg-amber-500/20 font-medium text-amber-300" : "text-muted-foreground hover:bg-accent"}`}>
              <span className="sm:hidden">Demo</span><span className="hidden sm:inline">Demonstração</span></button>
          </div>
          <div className="flex gap-1">
            <Button size="icon" variant="outline" aria-label="Aproximar" onClick={() => cena.current?.zoom(1.25)}><Plus className="size-4" /></Button>
            <Button size="icon" variant="outline" aria-label="Afastar" onClick={() => cena.current?.zoom(0.8)}><Minus className="size-4" /></Button>
            <Button size="icon" variant="outline" aria-label="Ver escritório inteiro" onClick={() => cena.current?.reset()}><Maximize2 className="size-4" /></Button>
          </div>
        </div>
      </header>

      {modo === "demo" ? (
        <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-xs text-amber-300 md:px-6" role="status">
          <b>DEMONSTRAÇÃO:</b> estados e tarefas abaixo são simulados.
          <span className="hidden sm:inline"> Volte para &quot;Dados reais&quot; para ver os agentes de verdade.</span>
          {pausado && " (pausado enquanto a aba está escondida)"}
        </div>
      ) : (
        <div className={`border-b px-4 py-1.5 text-xs md:px-6 ${CONEXAO[real.conexao].classe}`} role="status">
          {CONEXAO[real.conexao].texto}
          {real.estado && !real.estado.sistema.worker_ok && (
            <b> · Worker parado: os agendamentos estão atrasados. No Docker: docker compose -f docker-compose.prod.yml logs worker</b>
          )}
        </div>
      )}

      {modo === "real" && real.estado && real.statuses && <Kpis st={real.estado} statuses={real.statuses} />}

      <nav className="flex gap-1.5 overflow-x-auto border-b border-white/10 px-4 py-2 md:px-6" aria-label="Departamentos">
        {DEPARTAMENTOS.map((d) => (
          <button key={d.id} onClick={() => { setSel({ tipo: "dept", id: d.id }); cena.current?.focusDept(d.id); }}
            className={`flex shrink-0 items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs hover:border-[#c9a45c]/60 ${sel?.tipo === "dept" && sel.id === d.id ? "border-[#c9a45c] text-[#f0d9a3]" : ""}`}>
            <span className="size-2 rounded-full" style={{ background: DEPT_ESTADO_COR[depts[d.id].estado] }} />
            {d.nome}
            {depts[d.id].tarefas > 0 && <span className="rounded-full bg-muted px-1.5 text-[10px] tabular-nums">{depts[d.id].tarefas}</span>}
          </button>
        ))}
      </nav>

      <div className={`relative min-h-0 flex-1 ${pausado ? "office-paused" : ""}`}>
        <OfficeScene ref={cena} statuses={statuses} deptStatus={depts} selecionado={sel} onSelect={setSel} />

        <div className="pointer-events-none absolute bottom-3 left-3 z-10 hidden flex-wrap gap-x-3 gap-y-1 rounded-lg border border-white/10 bg-[#0b0f17]/80 px-3 py-2 text-[11px] text-slate-300 backdrop-blur sm:flex">
          {Object.entries(ESTADOS).map(([k, e]) => (
            <span key={k} className="flex items-center gap-1"><span className="size-2 rounded-full" style={{ background: e.cor }} />{e.rotulo}</span>
          ))}
        </div>

        {(agente || dept) && (
          <aside className="absolute inset-x-2 bottom-2 z-10 max-h-[60%] overflow-y-auto rounded-xl border border-[#c9a45c]/25 bg-[#0f1520]/90 p-4 shadow-2xl backdrop-blur-md sm:inset-x-auto sm:right-3 sm:top-3 sm:bottom-auto sm:w-80 sm:max-h-[calc(100%-1.5rem)]">
            <button className="absolute right-2 top-2 rounded p-1 hover:bg-accent" aria-label="Fechar" onClick={() => setSel(null)}><X className="size-4" /></button>
            {agente ? (
              <div className="space-y-3 text-sm">
                <div className="flex items-center gap-3 pr-6">
                  <Avatar agent={agente} />
                  <div><div className="font-semibold">{agente.nome}</div><div className="text-xs text-muted-foreground">{agente.cargo}</div></div>
                </div>
                <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-xs">
                  <dt className="text-muted-foreground">Departamento</dt><dd>{dept?.nome}</dd>
                  <dt className="text-muted-foreground">Modelo de IA</dt><dd>{agente.modelo}</dd>
                  <dt className="text-muted-foreground">Status</dt><dd><EstadoBadge status={statuses[agente.id]} /></dd>
                  <dt className="text-muted-foreground">Tarefa atual</dt><dd>{statuses[agente.id].tarefa ?? "—"}</dd>
                  <dt className="text-muted-foreground">Última atividade</dt><dd>{desde(statuses[agente.id].desde)}</dd>
                  <dt className="text-muted-foreground">Agente real</dt><dd className="break-all font-mono">{agente.jobTypes.join(", ")}</dd>
                </dl>
                {selo}
                {modo === "real"
                  ? <div className="border-t pt-3"><div className="mb-2 text-xs font-medium">Histórico</div><HistoricoAgente agent={agente} /></div>
                  : <p className="text-xs text-muted-foreground">Na demonstração não há histórico. Mude para &quot;Dados reais&quot;.</p>}
              </div>
            ) : dept && (
              <div className="space-y-3 text-sm">
                <div className="pr-6">
                  <div className="flex items-center gap-2 font-semibold"><span className="size-3 rounded" style={{ background: dept.cor }} />{dept.nome}</div>
                  <p className="mt-1 text-xs text-muted-foreground">{dept.descricao}</p>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-md border p-2"><div className="text-[11px] text-muted-foreground">Estado</div>
                    <div className="mt-0.5 flex items-center justify-center gap-1 text-xs font-medium">
                      <span className="size-2 rounded-full" style={{ background: DEPT_ESTADO_COR[depts[dept.id].estado] }} />{depts[dept.id].estado}</div></div>
                  <div className="rounded-md border p-2"><div className="text-[11px] text-muted-foreground">Tarefas</div><div className="font-semibold">{depts[dept.id].tarefas}</div></div>
                  <div className="rounded-md border p-2"><div className="text-[11px] text-muted-foreground">Ativos</div><div className="font-semibold">{depts[dept.id].ativos}</div></div>
                </div>
                <ul className="space-y-1.5">
                  {AGENTES.filter((a) => a.departamento === dept.id).map((a) => (
                    <li key={a.id}>
                      <button className="flex w-full items-center gap-2 rounded-md p-1.5 text-left hover:bg-accent" onClick={() => setSel({ tipo: "agente", id: a.id })}>
                        <Avatar agent={a} size={32} />
                        <span className="min-w-0 flex-1"><span className="block text-xs font-medium">{a.nome}</span>
                          <span className="block truncate text-[11px] text-muted-foreground">{statuses[a.id].tarefa ?? a.cargo}</span></span>
                        <EstadoBadge status={statuses[a.id]} />
                      </button>
                    </li>
                  ))}
                </ul>
                {selo}
              </div>
            )}
          </aside>
        )}
      </div>

      {modo === "real" && <Feed eventos={real.eventos} aberto={feedAberto} setAberto={setFeedAberto} />}
    </div>
  );
}
