"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Activity, AlertTriangle, ArrowRight, BadgeCheck, BookOpen, Bot, Briefcase, Building2, CheckCircle2, Filter, Gauge, Handshake,
  Info, MessageCircle, Send, ShieldCheck, Sparkles, Target, TrendingUp, Users,
} from "lucide-react";
import { BarList, Donut, Legenda, SERIE, TrendChart } from "@/components/charts";
import { KpiCard, Secao } from "@/components/kpi-card";
import { ErrorBox } from "@/components/page-header";
import { useApi } from "@/components/use-api";
import { SEVERIDADE, type Pendencia } from "@/lib/alerts";
import { categoriaLabel, editionStatusLabel, fmtDate } from "@/lib/format";
import { TOM } from "@/lib/nav";
import type { Overview } from "@/lib/overview";
import { porFase } from "@/lib/pipeline";
import { cn } from "@/lib/utils";
import { AGENTES, DEPARTAMENTOS } from "@/office/config";
import type { DashboardSummary } from "@/lib/types";

const n = (v: number | string | null | undefined) => Number(v ?? 0).toLocaleString("pt-BR");
const ICONE: Record<Pendencia["severidade"], typeof Info> = { critico: AlertTriangle, aviso: AlertTriangle, oportunidade: Sparkles, info: Info };

const WA = [
  { chave: "human_confirmed", rotulo: "Confirmado por pessoa", cor: SERIE(6) },
  { chave: "company_evidence", rotulo: "Publicado pela empresa", cor: SERIE(3) },
  { chave: "candidate", rotulo: "Candidato (celular)", cor: SERIE(4) },
  { chave: "found", rotulo: "Encontrado", cor: SERIE(1) },
  { chave: "invalid", rotulo: "Inválido", cor: SERIE(8) },
];
const SERIES = [
  { chave: "leads", rotulo: "Leads novos", cor: SERIE(1) },
  { chave: "contatos", rotulo: "Contatos encontrados", cor: SERIE(2) },
  { chave: "whatsapp", rotulo: "WhatsApp encontrados", cor: SERIE(3) },
];

function saudacao() {
  const h = new Date().getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}

function Prioridades({ itens }: { itens: Pendencia[] | undefined }) {
  if (!itens) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  if (!itens.length) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 py-8 text-center">
        <span className="grid size-12 place-items-center rounded-full bg-emerald-500/10 text-[var(--success)]"><CheckCircle2 className="size-6" /></span>
        <div className="font-medium">Tudo em dia</div>
        <p className="text-sm text-muted-foreground">Nenhuma pendência agora. Os agentes seguem trabalhando.</p>
      </div>
    );
  }
  return (
    <ul className="space-y-2">
      {itens.slice(0, 7).map((p) => {
        const s = SEVERIDADE[p.severidade];
        const I = ICONE[p.severidade];
        return (
          <li key={p.chave}>
            <Link href={p.href} className="group flex items-center gap-3 rounded-xl border border-transparent p-2.5 transition-colors hover:border-border hover:bg-accent/40">
              <span className={cn("grid size-9 shrink-0 place-items-center rounded-lg", s.fundo, s.texto)}><I className="size-4" /></span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{p.titulo}</span>
                <span className={cn("eyebrow text-[9px]", s.texto)}>{s.rotulo}</span>
              </span>
              <span className="num text-lg font-semibold">{n(p.quantidade)}</span>
              <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function Funil({ o }: { o: Overview }) {
  const fases = porFase(o.pipeline);
  const max = Math.max(1, ...fases.map((f) => f.total));
  const cores = [SERIE(1), SERIE(7), SERIE(2), SERIE(5), SERIE(3)];
  return (
    <div className="space-y-3">
      {fases.map((f, k) => (
        <div key={f.fase}>
          <div className="mb-1 flex items-baseline justify-between text-sm">
            <span className="font-medium">{f.fase}</span>
            <span className="num font-semibold">{n(f.total)}</span>
          </div>
          <div className="flex h-7 overflow-hidden rounded-lg bg-muted" style={{ width: `${Math.max(14, (f.total / max) * 100)}%` }}>
            {f.etapas.filter((e) => e.n > 0).map((e, i, arr) => (
              <Link key={e.id} href={`/pipeline?etapa=${e.id}`} title={`${e.nome}: ${n(e.n)}`}
                className="h-full transition-opacity hover:opacity-80"
                style={{ width: `${(e.n / f.total) * 100}%`, background: cores[k], opacity: 1 - i * (0.55 / Math.max(1, arr.length)),
                  borderRight: i < arr.length - 1 ? "2px solid var(--card)" : undefined }} />
            ))}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-muted-foreground">
            {f.etapas.filter((e) => e.n > 0).map((e) => <span key={e.id}>{e.nome} <b className="num text-foreground">{n(e.n)}</b></span>)}
          </div>
        </div>
      ))}
    </div>
  );
}

function Agentes({ o }: { o: Overview }) {
  const linhas = AGENTES.filter((a) => !a.lider).map((a) => {
    const st = a.jobTypes.map((t) => o.agentes[t]).filter(Boolean);
    const ex = st.reduce((s, x) => s + x.execucoes, 0), ok = st.reduce((s, x) => s + x.sucesso, 0), fa = st.reduce((s, x) => s + x.falhas, 0);
    const ult = st.map((x) => x.ultima_execucao).filter(Boolean).sort().pop() ?? null;
    return { a, ex, ok, fa, ult, taxa: ex ? Math.round((ok / ex) * 100) : null, dep: DEPARTAMENTOS.find((d) => d.id === a.departamento)! };
  }).sort((x, y) => y.ex - x.ex);
  return (
    <ul className="divide-y">
      {linhas.map(({ a, ex, fa, ult, taxa, dep }) => (
        <li key={a.id} className="flex items-center gap-3 py-2">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg text-xs font-bold text-white" style={{ background: dep.cor }}>{a.nome.slice(0, 2)}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{a.nome} <span className="font-normal text-muted-foreground">· {a.cargo}</span></span>
            <span className="text-[11px] text-muted-foreground">{ult ? `última execução ${fmtDate(ult)}` : "sem execuções no período"}</span>
          </span>
          <span className="hidden w-24 sm:block">
            <span className="block h-1.5 overflow-hidden rounded-full bg-muted">
              <span className="block h-full rounded-full" style={{ width: `${taxa ?? 0}%`, background: fa ? "var(--warning)" : "var(--success)" }} />
            </span>
          </span>
          <span className="num w-20 text-right text-sm"><b>{n(ex)}</b><span className="text-xs text-muted-foreground"> exec.</span></span>
          <span className={cn("num w-14 text-right text-xs", fa ? "font-semibold text-red-600" : "text-muted-foreground")}>{fa ? `${fa} falha${fa > 1 ? "s" : ""}` : taxa !== null ? `${taxa}% ok` : "—"}</span>
        </li>
      ))}
    </ul>
  );
}

function IndicadoresOperacionais({ s }: { s: DashboardSummary | null }) {
  const itens: [keyof DashboardSummary, string, string][] = [
    ["processos_importados", "Processos importados", "/processos"],
    ["processos_sem_procurador", "Sem procurador", "/processos?oportunidade=elegivel"],
    ["procurador_ausente_confirmado", "Ausência confirmada no INPI", "/processos?procurador_status=sem_confirmado"],
    ["processos_descartados", "Descartados", "/processos?oportunidade=descartada"],
    ["leads_encontrados", "Leads encontrados", "/leads"],
    ["leads_sem_contato", "Leads sem contato", "/leads?status=sem_contato"],
    ["contatos_validados", "Contatos validados", "/contatos"],
    ["leads_whatsapp_validado", "Leads com WhatsApp validado", "/leads?whatsapp=validado"],
    ["pesquisas_pendentes", "Pesquisas pendentes", "/jobs?status=queued"],
    ["agentes_em_execucao", "Agentes em execução", "/jobs?status=running"],
    ["revisoes_abertas", "Revisões abertas", "/revisoes"],
    ["custo_ia_semana_usd", "Custo de IA na semana (US$)", "/operacao"],
  ];
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-3 lg:grid-cols-6">
      {itens.map(([k, rot, href]) => (
        <Link key={k} href={href} className="bg-card px-4 py-3 transition-colors hover:bg-accent/40">
          <div className="truncate text-[11px] text-muted-foreground">{rot}</div>
          <div className="num mt-0.5 text-lg font-semibold">{s ? (k === "custo_ia_semana_usd" ? Number(s[k]).toFixed(2) : n(s[k])) : "…"}</div>
        </Link>
      ))}
    </div>
  );
}

export default function Dashboard() {
  const [dias, setDias] = useState(14);
  const ov = useApi<Overview>(`/api/dashboard/overview?dias=${dias}`, 30000);
  const summary = useApi<DashboardSummary>("/api/dashboard/summary", 30000);
  const o = ov.data;
  const k = o?.kpis;
  const serie = (c: "leads" | "contatos" | "whatsapp") => o?.series.map((s) => s[c]) ?? [];
  const parado = o?.pendencias.some((p) => p.chave === "worker");
  const ultimaRpi = o?.edicoes[0];

  return (
    <div className="space-y-6">
      <ErrorBox error={ov.error} />

      {/* faixa de abertura */}
      <section className="entrar relative overflow-hidden rounded-3xl bg-[radial-gradient(120%_140%_at_0%_0%,#4f46e5_0%,#6d28d9_45%,#1e1b4b_100%)] p-6 text-white shadow-xl shadow-indigo-900/20 md:p-8">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30 [mask-image:linear-gradient(to_left,black,transparent_70%)]" />
        <div className="relative flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-2xl">
            <div className="eyebrow text-indigo-200">Painel executivo</div>
            <h1 className="mt-1 text-2xl font-semibold md:text-3xl">{saudacao()}! Este é o pulso da sua operação.</h1>
            <p className="mt-2 text-sm text-indigo-100/90">
              {ultimaRpi ? <>Última RPI importada: <b>nº {ultimaRpi.numero}</b>{ultimaRpi.data_publicacao ? ` de ${new Date(ultimaRpi.data_publicacao + "T12:00").toLocaleDateString("pt-BR")}` : ""}. </> : "Nenhuma RPI importada ainda. "}
              {k ? <><b className="num">{n(k.executando)}</b> tarefa(s) em execução e <b className="num">{n(k.na_fila)}</b> na fila.</> : "Carregando…"}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link href="/escritorio" className="inline-flex items-center gap-2 rounded-lg bg-white px-3.5 py-2 text-sm font-medium text-indigo-700 shadow hover:bg-indigo-50"><Building2 className="size-4" /> Central de Operações IA</Link>
              <Link href="/pipeline" className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-3.5 py-2 text-sm font-medium text-white ring-1 ring-white/25 hover:bg-white/15"><Filter className="size-4" /> Pipeline comercial</Link>
              <button onClick={() => window.dispatchEvent(new Event("inpi:busca"))} className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-3.5 py-2 text-sm font-medium text-white ring-1 ring-white/25 hover:bg-white/15"><Sparkles className="size-4" /> Ações rápidas <kbd className="hidden rounded bg-white/15 px-1 font-mono text-[10px] sm:inline">Ctrl K</kbd></button>
            </div>
          </div>
          <Link href="/escritorio" className="flex w-full max-w-xs items-center gap-3 rounded-2xl bg-white/10 p-3 ring-1 ring-white/20 backdrop-blur transition-colors hover:bg-white/15 sm:w-auto">
            <span className="grid size-11 place-items-center rounded-xl bg-gradient-to-br from-amber-300 to-fuchsia-400 text-base font-bold text-indigo-950">S</span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold">SILVANE · Diretoria</span>
              <span className="flex items-center gap-1.5 text-xs text-indigo-100">
                <span className={cn("size-2 rounded-full", parado ? "bg-red-400" : "pulso bg-emerald-400")} />
                {o ? (parado ? "Atenção: agenda atrasada" : "Operação normal") : "Conectando…"}
              </span>
            </span>
          </Link>
        </div>
      </section>

      {/* indicadores principais */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3 min-[1800px]:grid-cols-6">
        <KpiCard rotulo="Oportunidades INPI" valor={k ? n(k.oportunidades) : "…"} icon={Target} tom="indigo" href="/processos?oportunidade=elegivel"
          contexto={k && <>de <b className="num text-foreground">{n(k.processos)}</b> processos importados</>} />
        <KpiCard rotulo="Leads ativos" valor={k ? n(k.leads) : "…"} icon={Users} tom="orange" href="/leads" tendencia={serie("leads")}
          contexto={k && <><b className="num text-foreground">+{n(k.leads_7d)}</b> nos últimos 7 dias</>} />
        <KpiCard rotulo="WhatsApp validados" valor={k ? n(k.whatsapp_validado) : "…"} icon={MessageCircle} tom="emerald" href="/contatos?filtro=wa_empresa" tendencia={serie("whatsapp")}
          contexto={k && <>de <b className="num text-foreground">{n(k.whatsapp_total)}</b> números encontrados</>} />
        <KpiCard rotulo="Autorizações ativas" valor={k ? n(k.autorizacoes) : "…"} icon={ShieldCheck} tom="cyan" href="/contatos?filtro=com_permissao"
          contexto="Contatos que permitiram mensagens" />
        <KpiCard rotulo="Mensagens enviadas" valor={k ? n(k.enviadas + k.contatos_manuais) : "…"} icon={Send} tom="blue" href="/whatsapp"
          contexto={k && <><b className="num text-foreground">{n(k.entregues)}</b> entregues · <b className="num text-foreground">{n(k.respostas)}</b> respostas</>} />
        <KpiCard rotulo="Em negociação" valor={k ? n(k.em_negociacao) : "…"} icon={Handshake} tom="rose" href="/pipeline?etapa=interessado"
          contexto={k && <><b className="num text-foreground">{n(k.fechados)}</b> fechados · conversão {k.taxa_conversao === null ? "—" : `${k.taxa_conversao}%`}</>} />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Secao titulo="Evolução da prospecção" subtitulo="Quantidade nova por dia" icon={TrendingUp} className="xl:col-span-2"
          acao={
            <div className="flex rounded-lg border bg-muted/50 p-0.5 text-xs" role="radiogroup" aria-label="Período">
              {[7, 14, 30].map((d) => (
                <button key={d} role="radio" aria-checked={dias === d} onClick={() => setDias(d)}
                  className={cn("rounded-md px-2.5 py-1 font-medium", dias === d ? "bg-card shadow-sm" : "text-muted-foreground hover:text-foreground")}>{d} dias</button>
              ))}
            </div>
          }>
          <div className="mb-3"><Legenda itens={SERIES.map((s) => ({ rotulo: s.rotulo, cor: s.cor, valor: n(o?.series.reduce((t, x) => t + x[s.chave as "leads"], 0)) }))} /></div>
          {o ? <TrendChart dados={o.series} series={SERIES} /> : <div className="h-[220px] animate-pulse rounded-xl bg-muted" />}
        </Secao>
        <Secao titulo="Prioridades de hoje" subtitulo="O que pede sua atenção, do mais urgente ao menos" icon={Gauge}>
          <Prioridades itens={o?.pendencias} />
        </Secao>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 2xl:grid-cols-3">
        <Secao titulo="Funil comercial" subtitulo="Leads por fase do pipeline. Clique para abrir a etapa." icon={Filter}
          acao={<Link href="/pipeline" className="text-xs font-medium text-primary hover:underline">Abrir pipeline</Link>}>
          {o ? (o.pipeline.length ? <Funil o={o} /> : <p className="py-6 text-center text-sm text-muted-foreground">Os leads aparecem aqui assim que forem montados.</p>) : null}
        </Secao>
        <Secao titulo="Qualidade dos WhatsApp" subtitulo="Nível de comprovação dos números encontrados" icon={BadgeCheck}
          acao={<Link href="/contatos?filtro=whatsapp" className="text-xs font-medium text-primary hover:underline">Ver contatos</Link>}>
          {o && (o.whatsapp_niveis.length
            ? <Donut rotuloCentro="números" itens={WA.map((w) => ({ rotulo: w.rotulo, cor: w.cor, n: o.whatsapp_niveis.find((x) => x.chave === w.chave)?.n ?? 0 }))} />
            : <p className="py-6 text-center text-sm text-muted-foreground">Nenhum WhatsApp encontrado ainda. A pesquisa gratuita roda a cada hora.</p>)}
        </Secao>
        <Secao titulo="Leads por tipo de despacho" subtitulo="Origem das oportunidades" icon={Briefcase} className="lg:col-span-2 2xl:col-span-1">
          {o && <BarList cor={SERIE(7)} itens={o.categorias.map((c) => ({ chave: c.chave, rotulo: categoriaLabel[c.chave] ?? c.chave, n: c.n }))}
            href={(c) => `/leads?categoria=${c}`} />}
        </Secao>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Secao titulo="Desempenho dos agentes" subtitulo="Execuções e falhas nos últimos 7 dias" icon={Bot} className="xl:col-span-2"
          acao={<Link href="/escritorio" className="text-xs font-medium text-primary hover:underline">Central de Operações</Link>}>
          {o && <Agentes o={o} />}
        </Secao>
        <div className="flex flex-col gap-6">
          <Secao titulo="Leads por estado" subtitulo="Os 8 estados com mais leads" icon={Activity}>
            {o && <BarList cor={SERIE(1)} itens={o.ufs.map((u) => ({ chave: u.chave, rotulo: u.chave, n: u.n }))} />}
          </Secao>
          <Secao titulo="Edições da RPI" icon={BookOpen} acao={<Link href="/rpi" className="text-xs font-medium text-primary hover:underline">Todas</Link>}>
            <ul className="divide-y text-sm">
              {o?.edicoes.length === 0 && <li className="py-2 text-muted-foreground">Nenhuma edição importada.</li>}
              {o?.edicoes.map((e) => (
                <li key={e.numero} className="flex items-center gap-3 py-2">
                  <span className={cn("grid size-9 place-items-center rounded-lg text-xs font-bold", TOM.blue.suave, TOM.blue.texto)}>{e.numero}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{e.data_publicacao ? new Date(e.data_publicacao + "T12:00").toLocaleDateString("pt-BR") : "—"}</span>
                    <span className="text-xs text-muted-foreground">{e.processos ? `${n(e.processos)} processos` : "—"}</span>
                  </span>
                  <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", e.status === "parsed" ? "bg-emerald-500/10 text-emerald-700" : e.status === "error" ? "bg-red-500/10 text-red-700" : "bg-sky-500/10 text-sky-700")}>
                    {editionStatusLabel[e.status] ?? e.status}
                  </span>
                </li>
              ))}
            </ul>
          </Secao>
        </div>
      </div>

      <section className="entrar">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="eyebrow text-muted-foreground">Indicadores operacionais</h2>
          <span className="text-xs text-muted-foreground">{o ? `Atualizado ${fmtDate(o.gerado_em)} · a cada 30 s` : ""}</span>
        </div>
        <IndicadoresOperacionais s={summary.data} />
      </section>
    </div>
  );
}
