"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Activity, ArrowRight, Bot, CheckCircle2, ChevronDown, ChevronUp, Clock, Crown, ExternalLink, History, LayoutGrid, Map as MapIcon, Maximize2, Minus, Play, Plus, Search, Timer, X, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SPRITE_H, SPRITE_W, SpriteDefs } from "@/office/components/agent-sprite";
import { OfficeScene, type OfficeSceneHandle } from "@/office/components/office-scene";
import { AGENTES, DEPARTAMENTOS, ESTADOS } from "@/office/config";
import { DEPT_ESTADO_COR } from "@/office/demo";
import { agentOfEvent, type OfficeEvent, type OfficeState } from "@/office/real";
import type { Agent, AgentStatus, DeptStatus } from "@/office/types";
import { useDemoOffice } from "@/office/use-demo";
import { useRealOffice, type Conexao } from "@/office/use-real";
import { OperacaoSemanal } from "@/components/operacao-semanal";
import { ServicosResumo } from "@/components/servicos-resumo";
import { api } from "@/lib/api";
import type { Eu } from "@/lib/auth";
import { cn } from "@/lib/utils";
import "@/office/office.css";

type Sel = { tipo: "agente" | "dept"; id: string } | null;
type Modo = "real" | "demo";
type Vista = "central" | "escritorio";
type Stats = Record<string, { execucoes: number; sucesso: number; falhas: number; duracao_media_s: number | null; ultima_execucao: string | null; taxa_sucesso: number | null }>;

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


/** Estados reais em linguagem de operação (a cena mantém os rótulos técnicos da legenda). */
const ESTADO_PT: Record<string, { rotulo: string; classe: string }> = {
  idle: { rotulo: "Disponível", classe: "bg-slate-500/15 text-slate-300" },
  working: { rotulo: "Em execução", classe: "bg-emerald-500/15 text-emerald-300" },
  thinking: { rotulo: "Em execução · IA", classe: "bg-sky-500/15 text-sky-300" },
  waiting: { rotulo: "Com pendências", classe: "bg-amber-500/15 text-amber-300" },
  completed: { rotulo: "Concluiu agora", classe: "bg-teal-500/15 text-teal-300" },
  error: { rotulo: "Com falha", classe: "bg-red-500/15 text-red-300" },
};
const FILTROS_ESTADO: Record<string, { rotulo: string; casa: (s: string) => boolean }> = {
  todos: { rotulo: "Todos", casa: () => true },
  ativos: { rotulo: "Em execução", casa: (s) => s === "working" || s === "thinking" },
  pendencias: { rotulo: "Com pendências", casa: (s) => s === "waiting" },
  falha: { rotulo: "Com falha", casa: (s) => s === "error" },
  livres: { rotulo: "Disponíveis", casa: (s) => s === "idle" || s === "completed" },
};

function PillEstado({ status }: { status: AgentStatus }) {
  const e = ESTADO_PT[status.state];
  const vivo = status.state === "working" || status.state === "thinking";
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium", e.classe)}>
      <span className={cn("size-1.5 rounded-full bg-current", vivo && "pulso")} />{e.rotulo}
    </span>
  );
}

const dur = (s: number | null | undefined) => (s == null ? "—" : s < 60 ? `${Math.round(s)} s` : `${Math.round(s / 60)} min`);

function somaTipos(agent: Agent, st: OfficeState | null, stats: Stats | null) {
  const tipos = agent.jobTypes;
  const hoje = tipos.map((t) => st?.tipos[t]).filter(Boolean);
  const sem = tipos.map((t) => stats?.[t]).filter(Boolean) as Stats[string][];
  const ex = sem.reduce((a, x) => a + x.execucoes, 0), ok = sem.reduce((a, x) => a + x.sucesso, 0);
  const durs = sem.map((x) => x.duracao_media_s).filter((x): x is number => x != null);
  return {
    concluidas: hoje.reduce((a, x) => a + (x?.concluidos_hoje ?? 0), 0),
    falhas: hoje.reduce((a, x) => a + (x?.falhas_hoje ?? 0), 0),
    fila: hoje.reduce((a, x) => a + (x?.pendentes ?? 0) + (x?.executando ?? 0), 0),
    ex, taxa: ex ? Math.round((ok / ex) * 100) : null,
    duracao: durs.length ? durs.reduce((a, b) => a + Number(b), 0) / durs.length : null,
    ultima: sem.map((x) => x.ultima_execucao).filter(Boolean).sort().pop() ?? null,
  };
}

function Diretoria({ st, statuses, depts }: { st: OfficeState | null; statuses: Record<string, AgentStatus>; depts: Record<string, DeptStatus> }) {
  const silvane = AGENTES.find((a) => a.lider)!;
  const lista = AGENTES.filter((a) => !a.lider).map((a) => statuses[a.id]);
  const ok = st ? st.sistema.worker_ok : true;
  const nums: [string, string | number, string][] = [
    ["Agentes", AGENTES.length - 1, "na equipe"],
    ["Em execução", lista.filter((s) => s.state === "working" || s.state === "thinking").length, "agora"],
    ["Com pendências", lista.filter((s) => s.state === "waiting").length, "tarefas na fila"],
    ["Concluídas hoje", st ? st.kpis.concluidas_hoje.toLocaleString("pt-BR") : "—", "tarefas"],
    ["Falhas hoje", st ? st.kpis.falhas_hoje : "—", st?.kpis.falhas_hoje ? "revisar" : "nenhuma"],
  ];
  const setores = DEPARTAMENTOS.filter((d) => d.id !== "diretoria");
  return (
    <section className="relative overflow-hidden rounded-2xl border border-[#c9a45c]/30 bg-[radial-gradient(110%_130%_at_0%_0%,#2e1f5e_0%,#151a2e_55%,#0f1320_100%)] p-5 shadow-2xl">
      <div className="pointer-events-none absolute -right-16 -top-16 size-64 rounded-full bg-[#c9a45c]/10 blur-3xl" />
      <div className="relative flex flex-wrap items-center gap-5">
        <div className="relative">
          <Avatar agent={silvane} size={84} />
          <span className="absolute -right-2 -top-2 grid size-7 place-items-center rounded-full bg-gradient-to-br from-[#f0d9a3] to-[#c9a45c] text-[#2b1d14] shadow-lg"><Crown className="size-4" /></span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="eyebrow text-[#e2c27c]">Diretoria</div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-semibold tracking-wide text-white">{silvane.nome}</h2>
            <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium", ok ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300")}>
              <span className={cn("size-1.5 rounded-full bg-current", ok && "pulso")} />{ok ? "Operação normal" : "Agenda atrasada"}
            </span>
          </div>
          <div className="text-sm text-slate-300">{silvane.cargo}</div>
          <p className="mt-1 max-w-2xl text-xs text-slate-400">{silvane.especialidade}</p>
        </div>
        <div className="grid w-full grid-cols-2 gap-2 sm:grid-cols-5 lg:w-auto">
          {nums.map(([k, v, sub]) => (
            <div key={k} className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2">
              <div className="text-[11px] text-slate-400">{k}</div>
              <div className="num text-xl font-semibold text-white">{v}</div>
              <div className="text-[10px] text-slate-500">{sub}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="relative mt-5 rounded-xl border border-white/10 bg-white/[0.03] p-4">
        <div className="eyebrow mb-3 text-[#e2c27c]">Resumo executivo · manifestação à oposição × recurso de indeferimento (SC → RS → PR)</div>
        <ServicosResumo escuro />
      </div>
      <div className="relative mt-5 rounded-xl border border-white/10 bg-white/[0.03] p-4">
        <div className="eyebrow mb-3 text-[#e2c27c]">Operação semanal da RPI · resultados vistos pela SILVANE</div>
        <OperacaoSemanal escuro />
      </div>
      {/* fluxo entre os setores: quem entrega trabalho para quem */}
      <div className="relative mt-5 border-t border-white/10 pt-4">
        <div className="eyebrow mb-2 text-slate-400">Fluxo de trabalho entre os agentes</div>
        <ol className="flex items-stretch gap-1 overflow-x-auto pb-1">
          {setores.map((d, i) => (
            <li key={d.id} className="flex items-center gap-1">
              <div className="min-w-32 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2" style={{ boxShadow: `inset 3px 0 0 ${d.cor}` }}>
                <div className="flex items-center gap-1.5 text-xs font-medium text-slate-100">
                  <span className="size-2 rounded-full" style={{ background: DEPT_ESTADO_COR[depts[d.id].estado] }} />{d.nome}
                </div>
                <div className="mt-0.5 text-[11px] text-slate-400">
                  {depts[d.id].tarefas ? <><b className="num text-slate-200">{depts[d.id].tarefas}</b> tarefa(s)</> : depts[d.id].estado}
                </div>
              </div>
              {i < setores.length - 1 && <ArrowRight className="size-4 shrink-0 text-slate-600" />}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function CardAgente({ agent, status, st, stats, onDetalhe, podeExecutar, onExecutar, modo }: {
  agent: Agent; status: AgentStatus; st: OfficeState | null; stats: Stats | null; modo: Modo;
  onDetalhe: () => void; podeExecutar: boolean; onExecutar: (tipo: string) => void;
}) {
  const dep = DEPARTAMENTOS.find((d) => d.id === agent.departamento)!;
  const m = somaTipos(agent, modo === "real" ? st : null, modo === "real" ? stats : null);
  const ocupado = status.state === "working" || status.state === "thinking";
  return (
    <article className="group relative flex flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#121827] p-4 transition-all hover:-translate-y-0.5 hover:border-white/20 hover:shadow-2xl"
      style={{ backgroundImage: `radial-gradient(120% 60% at 100% 0%, ${dep.cor}26, transparent 60%)` }}>
      <span className="absolute inset-x-0 top-0 h-[3px]" style={{ background: dep.cor }} />
      <div className="flex items-start gap-3">
        <div className={cn("rounded-xl p-0.5", ocupado && "ring-2 ring-emerald-400/60")}><Avatar agent={agent} size={52} /></div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <h3 className="truncate font-semibold text-white">{agent.nome}</h3>
            <PillEstado status={status} />
          </div>
          <div className="truncate text-xs text-slate-300">{agent.cargo}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            <span className="rounded-full px-2 py-px text-[10px] font-medium text-white/90" style={{ background: `${dep.cor}cc` }}>{dep.nome}</span>
            <span className="rounded-full bg-white/5 px-2 py-px text-[10px] text-slate-400">{agent.modelo === "sem IA" ? "regras determinísticas" : agent.modelo}</span>
          </div>
        </div>
      </div>
      <p className="mt-3 line-clamp-2 min-h-8 text-xs text-slate-400">{agent.especialidade}</p>
      <div className={cn("mt-3 flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs", ocupado ? "bg-emerald-500/10 text-emerald-200" : status.state === "error" ? "bg-red-500/10 text-red-200" : "bg-white/[0.04] text-slate-300")}>
        <Activity className="size-3.5 shrink-0" />
        <span className="min-w-0 flex-1 truncate" title={status.tarefa ?? ""}>{status.tarefa ?? "Sem tarefa no momento"}</span>
        <span className="shrink-0 text-[10px] text-slate-500">{desde(status.desde)}</span>
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-white/[0.03] py-1.5"><dt className="flex items-center justify-center gap-1 text-[10px] text-slate-500"><CheckCircle2 className="size-3" />Hoje</dt><dd className="num text-sm font-semibold text-white">{m.concluidas}</dd></div>
        <div className="rounded-lg bg-white/[0.03] py-1.5"><dt className="flex items-center justify-center gap-1 text-[10px] text-slate-500"><Clock className="size-3" />Na fila</dt><dd className="num text-sm font-semibold text-white">{m.fila}</dd></div>
        <div className={cn("rounded-lg py-1.5", m.falhas ? "bg-red-500/10" : "bg-white/[0.03]")}><dt className="flex items-center justify-center gap-1 text-[10px] text-slate-500"><XCircle className="size-3" />Falhas</dt><dd className={cn("num text-sm font-semibold", m.falhas ? "text-red-300" : "text-white")}>{m.falhas}</dd></div>
      </dl>
      <div className="mt-3">
        <div className="mb-1 flex justify-between text-[10px] text-slate-500"><span>7 dias · {m.ex.toLocaleString("pt-BR")} execuções</span><span className="flex items-center gap-1"><Timer className="size-3" />{dur(m.duracao)}</span></div>
        <div className="h-1.5 overflow-hidden rounded-full bg-white/5"><div className="h-full rounded-full" style={{ width: `${m.taxa ?? 0}%`, background: (m.taxa ?? 100) < 90 ? "#f59e0b" : "#10b981" }} /></div>
        <div className="mt-1 text-[10px] text-slate-500">{m.taxa === null ? "Sem execuções no período" : `${m.taxa}% de sucesso`}</div>
      </div>
      <div className="mt-auto flex flex-wrap gap-1.5 pt-3">
        <button onClick={onDetalhe} className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2.5 py-1 text-xs text-slate-200 hover:bg-white/10"><History className="size-3.5" />Histórico</button>
        {agent.modulo && <Link href={agent.modulo.href} className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2.5 py-1 text-xs text-slate-200 hover:bg-white/10"><ExternalLink className="size-3.5" />{agent.modulo.rotulo}</Link>}
        {podeExecutar && agent.executar && modo === "real" && (
          <button onClick={() => onExecutar(agent.executar!)} className="ml-auto inline-flex items-center gap-1 rounded-lg bg-[#c9a45c]/15 px-2.5 py-1 text-xs font-medium text-[#f0d9a3] hover:bg-[#c9a45c]/25" title="Coloca uma execução na fila agora">
            <Play className="size-3.5" />Executar
          </button>
        )}
      </div>
    </article>
  );
}

function Central({ modo, st, statuses, depts, onDetalhe }: {
  modo: Modo; st: OfficeState | null; statuses: Record<string, AgentStatus>; depts: Record<string, DeptStatus>; onDetalhe: (id: string) => void;
}) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [eu, setEu] = useState<Eu | null>(null);
  const [setor, setSetor] = useState("todos");
  const [estado, setEstado] = useState("todos");
  const [q, setQ] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  useEffect(() => {
    let vivo = true;
    const load = () => api<{ tipos: Stats }>("/api/office/stats?dias=7").then((r) => vivo && setStats(r.tipos)).catch(() => undefined);
    load();
    api<Eu>("/api/auth/me").then((r) => vivo && setEu(r)).catch(() => undefined);
    const t = setInterval(load, 30000);
    return () => { vivo = false; clearInterval(t); };
  }, []);
  const executar = async (tipo: string) => {
    setAviso(null);
    try {
      await api("/api/jobs", { method: "POST", body: JSON.stringify({ tipo, payload: {}, dedupe_key: tipo }) });
      setAviso(`Execução de ${tipo} colocada na fila. O status do agente muda em instantes.`);
    } catch (e) { setAviso(e instanceof Error ? e.message : String(e)); }
  };
  const termo = q.trim().toLowerCase();
  const equipe = AGENTES.filter((a) => !a.lider)
    .filter((a) => setor === "todos" || a.departamento === setor)
    .filter((a) => FILTROS_ESTADO[estado].casa(statuses[a.id].state))
    .filter((a) => !termo || `${a.nome} ${a.cargo} ${a.especialidade ?? ""}`.toLowerCase().includes(termo));

  return (
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
      <svg width={0} height={0} className="absolute" aria-hidden><SpriteDefs /></svg>
      <div className="space-y-5 p-4 md:p-6">
        <Diretoria st={modo === "real" ? st : null} statuses={statuses} depts={depts} />
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap gap-1.5">
            {[{ id: "todos", nome: "Todos os setores", cor: "#64748b" }, ...DEPARTAMENTOS.filter((d) => d.id !== "diretoria")].map((d) => (
              <button key={d.id} onClick={() => setSetor(d.id)}
                className={cn("flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs", setor === d.id ? "border-[#c9a45c] bg-[#c9a45c]/10 text-[#f0d9a3]" : "border-white/10 bg-white/[0.03] text-slate-300 hover:border-white/25")}>
                <span className="size-2 rounded-full" style={{ background: d.cor }} />{d.nome}
              </button>
            ))}
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-white/10 p-0.5 text-xs">
              {Object.entries(FILTROS_ESTADO).map(([k, f]) => (
                <button key={k} onClick={() => setEstado(k)} className={cn("rounded-md px-2.5 py-1", estado === k ? "bg-white/10 font-medium text-white" : "text-slate-400 hover:text-white")}>{f.rotulo}</button>
              ))}
            </div>
            <label className="flex h-8 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 text-xs text-slate-300">
              <Search className="size-3.5" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar agente" className="w-28 bg-transparent outline-none placeholder:text-slate-500" />
            </label>
          </div>
        </div>
        {aviso && <div className="rounded-xl border border-[#c9a45c]/30 bg-[#c9a45c]/10 px-3 py-2 text-xs text-[#f0d9a3]">{aviso}</div>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 min-[1800px]:grid-cols-4">
          {equipe.map((a) => (
            <CardAgente key={a.id} agent={a} status={statuses[a.id]} st={st} stats={stats} modo={modo}
              onDetalhe={() => onDetalhe(a.id)} podeExecutar={eu?.papel === "admin"} onExecutar={executar} />
          ))}
          {!equipe.length && <p className="col-span-full py-10 text-center text-sm text-slate-400">Nenhum agente com esses filtros.</p>}
        </div>
      </div>
    </div>
  );
}

export default function EscritorioPage() {
  const [modo, setModo] = useState<Modo>("real");
  const [vista, setVista] = useState<Vista>("central");
  const demo = useDemoOffice();
  const real = useRealOffice(modo === "real");
  const [sel, setSel] = useState<Sel>(null);
  const [feedAberto, setFeedAberto] = useState(false);
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
    <div className="dark -m-4 flex h-[calc(100dvh-3.5rem)] flex-col bg-[#0b0f17] text-foreground md:-m-6 lg:-m-8">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-gradient-to-r from-[#111827] to-[#0b0f17] px-4 py-3 md:px-6">
        <div>
          <div className="eyebrow bg-gradient-to-r from-[#f0d9a3] to-[#c9a45c] bg-clip-text text-transparent">INPI AI OFFICE</div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-white"><Bot className="size-5 text-[#e2c27c]" />Central de Operações IA</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-white/10 bg-white/[0.03] p-0.5 text-xs" role="tablist" aria-label="Visualização">
            <button role="tab" aria-selected={vista === "central"} onClick={() => setVista("central")}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 ${vista === "central" ? "bg-[#c9a45c]/20 font-medium text-[#f0d9a3]" : "text-muted-foreground hover:bg-accent"}`}>
              <LayoutGrid className="size-3.5" />Equipe</button>
            <button role="tab" aria-selected={vista === "escritorio"} onClick={() => setVista("escritorio")}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 ${vista === "escritorio" ? "bg-[#c9a45c]/20 font-medium text-[#f0d9a3]" : "text-muted-foreground hover:bg-accent"}`}>
              <MapIcon className="size-3.5" />Escritório virtual</button>
          </div>
          <div className="flex rounded-md border p-0.5 text-xs" role="radiogroup" aria-label="Fonte dos dados">
            <button role="radio" aria-checked={modo === "real"} onClick={() => setModo("real")}
              className={`rounded px-2.5 py-1 ${modo === "real" ? "bg-emerald-500/20 font-medium text-emerald-300" : "text-muted-foreground hover:bg-accent"}`}>
              Dados reais</button>
            <button role="radio" aria-checked={modo === "demo"} onClick={() => setModo("demo")}
              className={`rounded px-2.5 py-1 ${modo === "demo" ? "bg-amber-500/20 font-medium text-amber-300" : "text-muted-foreground hover:bg-accent"}`}>
              <span className="sm:hidden">Demo</span><span className="hidden sm:inline">Demonstração</span></button>
          </div>
          {vista === "escritorio" && <div className="flex gap-1">
            <Button size="icon" variant="outline" aria-label="Aproximar" onClick={() => cena.current?.zoom(1.25)}><Plus className="size-4" /></Button>
            <Button size="icon" variant="outline" aria-label="Afastar" onClick={() => cena.current?.zoom(0.8)}><Minus className="size-4" /></Button>
            <Button size="icon" variant="outline" aria-label="Ver escritório inteiro" onClick={() => cena.current?.reset()}><Maximize2 className="size-4" /></Button>
          </div>}
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

      {vista === "central" && (
        <Central modo={modo} st={real.estado ?? null} statuses={statuses} depts={depts} onDetalhe={(id) => setSel({ tipo: "agente", id })} />
      )}
      {vista === "escritorio" && <nav className="flex gap-1.5 overflow-x-auto border-b border-white/10 px-4 py-2 md:px-6" aria-label="Departamentos">
        {DEPARTAMENTOS.map((d) => (
          <button key={d.id} onClick={() => { setSel({ tipo: "dept", id: d.id }); cena.current?.focusDept(d.id); }}
            className={`flex shrink-0 items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs hover:border-[#c9a45c]/60 ${sel?.tipo === "dept" && sel.id === d.id ? "border-[#c9a45c] text-[#f0d9a3]" : ""}`}>
            <span className="size-2 rounded-full" style={{ background: DEPT_ESTADO_COR[depts[d.id].estado] }} />
            {d.nome}
            {depts[d.id].tarefas > 0 && <span className="rounded-full bg-muted px-1.5 text-[10px] tabular-nums">{depts[d.id].tarefas}</span>}
          </button>
        ))}
      </nav>}

      <div className={cn("relative min-h-0", vista === "escritorio" ? "flex-1" : "h-0", pausado && "office-paused")}>
        {vista === "escritorio" && <OfficeScene ref={cena} statuses={statuses} deptStatus={depts} selecionado={sel} onSelect={setSel} />}

        {vista === "escritorio" && <div className="pointer-events-none absolute bottom-3 left-3 z-10 hidden flex-wrap gap-x-3 gap-y-1 rounded-lg border border-white/10 bg-[#0b0f17]/80 px-3 py-2 text-[11px] text-slate-300 backdrop-blur sm:flex">
          {Object.entries(ESTADOS).map(([k, e]) => (
            <span key={k} className="flex items-center gap-1"><span className="size-2 rounded-full" style={{ background: e.cor }} />{e.rotulo}</span>
          ))}
        </div>}

        {(agente || dept) && (
          <aside className="fixed inset-x-2 bottom-2 z-40 sm:absolute sm:z-10 max-h-[60%] overflow-y-auto rounded-xl border border-[#c9a45c]/25 bg-[#0f1520]/90 p-4 shadow-2xl backdrop-blur-md sm:inset-x-auto sm:right-3 sm:top-3 sm:bottom-auto sm:w-80 sm:max-h-[calc(100%-1.5rem)]" style={vista === "central" ? { position: "fixed", top: "4.5rem", maxHeight: "calc(100dvh - 5.5rem)" } : undefined}>
            <button className="absolute right-2 top-2 rounded p-1 hover:bg-accent" aria-label="Fechar" onClick={() => setSel(null)}><X className="size-4" /></button>
            {agente ? (
              <div className="space-y-3 text-sm">
                <div className="flex items-center gap-3 pr-6">
                  <Avatar agent={agente} />
                  <div><div className="flex items-center gap-1.5 font-semibold">{agente.lider && <Crown className="size-4 text-[#e2c27c]" />}{agente.nome}</div><div className="text-xs text-muted-foreground">{agente.cargo}</div></div>
                </div>
                <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-xs">
                  <dt className="text-muted-foreground">Departamento</dt><dd>{dept?.nome}</dd>
                  <dt className="text-muted-foreground">Modelo de IA</dt><dd>{agente.modelo}</dd>
                  <dt className="text-muted-foreground">Status</dt><dd><EstadoBadge status={statuses[agente.id]} /></dd>
                  <dt className="text-muted-foreground">Tarefa atual</dt><dd>{statuses[agente.id].tarefa ?? "—"}</dd>
                  <dt className="text-muted-foreground">Última atividade</dt><dd>{desde(statuses[agente.id].desde)}</dd>
                  <dt className="text-muted-foreground">Agente real</dt><dd className="break-all font-mono">{agente.jobTypes.join(", ")}</dd>
                </dl>
                {agente.especialidade && <p className="text-xs text-slate-300">{agente.especialidade}</p>}
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
