"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, CalendarClock, Check, CheckCircle2, Clock, Crown, Flame, Loader2, RefreshCw, Radar, X } from "lucide-react";
import { BarList, Legenda, SERIE } from "@/components/charts";
import { Secao } from "@/components/kpi-card";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { Select } from "@/components/select";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi } from "@/components/use-api";
import { api } from "@/lib/api";
import { BRASIL_UFS } from "@/lib/brasil-geo";
import { fmtDate, fmtDay } from "@/lib/format";
import { ETAPA_STATUS, TEMPERATURA, responsavel, type Relatorio, type Semana, type StatusEtapa } from "@/lib/territorio";
import { cn } from "@/lib/utils";
import { formatWhats } from "@/lib/whatsapp";

const n = (v: number | null | undefined) => Number(v ?? 0).toLocaleString("pt-BR");
const NOME = Object.fromEntries([...BRASIL_UFS.map((u) => [u.uf, u.nome]), ["PENDENTE", "Localização pendente"]]);
const DIAS = ["", "seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
const ICONE: Record<StatusEtapa, typeof Check> = { concluida: Check, em_execucao: Loader2, pendente: Clock, erro: X, sem_dados: Clock };

function Linha({ etapas }: { etapas: NonNullable<Semana["status"]>["etapas"] }) {
  return (
    <ol className="flex flex-col gap-3 md:flex-row md:items-start md:gap-0">
      {etapas.map((e, i) => {
        const s = ETAPA_STATUS[e.status];
        const I = ICONE[e.status];
        return (
          <li key={e.chave} className="flex flex-1 items-center gap-3 md:flex-col md:items-center md:text-center">
            <div className="flex w-full items-center md:justify-center">
              <span className={cn("hidden h-0.5 flex-1 md:block", i === 0 ? "bg-transparent" : etapas[i - 1].status === "concluida" ? "bg-emerald-400" : "bg-border")} />
              <span className={cn("grid size-9 shrink-0 place-items-center rounded-full shadow-sm ring-4 ring-card", s.classe)}>
                <I className={cn("size-4", e.status === "em_execucao" && "animate-spin")} />
              </span>
              <span className={cn("hidden h-0.5 flex-1 md:block", i === etapas.length - 1 ? "bg-transparent" : e.status === "concluida" ? "bg-emerald-400" : "bg-border")} />
            </div>
            <div className="min-w-0 md:mt-2">
              <div className="text-sm font-semibold">{e.chave.length === 2 ? NOME[e.chave] : e.nome}</div>
              <div className="text-[11px] text-muted-foreground">{s.rotulo}{e.em ? ` · ${fmtDate(e.em)}` : ""}</div>
              {e.dados && <div className="num text-[11px] text-muted-foreground">{n(e.dados.leads)} lead(s) · {n(e.dados.quentes)} quente(s)</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function RelatorioCard({ numero }: { numero: string }) {
  const [uf, setUf] = useState("SC");
  const q = new URLSearchParams({ uf });
  if (numero) q.set("numero", numero);
  const { data: r, error } = useApi<Relatorio>(`/api/rpi-semana/relatorio?${q}`, 30000);
  return (
    <Secao titulo="Relatório executivo do estado" subtitulo="O de Santa Catarina sai primeiro na terça-feira" icon={Crown}
      acao={<Select value={uf} onChange={setUf} options={Object.fromEntries(["SC", "RS", "PR", ...BRASIL_UFS.map((u) => u.uf).filter((x) => !["SC", "RS", "PR"].includes(x))].map((u) => [u, `${u} · ${NOME[u]}`]))} className="h-8 text-xs" />}>
      <ErrorBox error={error} />
      {r && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {([["Oposições apresentadas", r.oposicoes], ["Novas oportunidades", r.novas_oportunidades], ["Contatos validados", r.contatos_validados], ["Leads quentes", r.total_quentes]] as const).map(([k, v]) => (
              <div key={k} className="rounded-xl border bg-card p-3"><div className="text-[11px] text-muted-foreground">{k}</div><div className="num text-2xl font-semibold">{n(v)}</div></div>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className={cn("rounded-full px-2 py-0.5 font-medium", ETAPA_STATUS[r.situacao].classe)}>{ETAPA_STATUS[r.situacao].rotulo}</span>
            <span className="text-muted-foreground">RPI nº {r.edicao.numero} · {fmtDay(r.edicao.data_publicacao)} · {n(r.publicados_oposicao)} pedido(s) publicados para oposição</span>
          </div>
          <div>
            <div className="mb-1.5 text-sm font-semibold">Leads quentes para abordagem</div>
            {r.leads_quentes.length === 0 ? <p className="text-sm text-muted-foreground">Ainda nenhum lead quente. Quente = oportunidade relevante, recente e com contato validado.</p> : (
              <ul className="divide-y rounded-xl border">
                {r.leads_quentes.map((l) => (
                  <li key={l.id}><Link href={`/leads/${l.id}`} className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-accent/40">
                    <Flame className="size-4 text-rose-500" />
                    <span className="min-w-0 flex-1"><span className="block truncate font-medium">{l.titular}</span><span className="block truncate text-[11px] text-muted-foreground">{l.marcas ?? "—"}{l.municipio ? ` · ${l.municipio}` : ""}</span></span>
                    {l.whatsapp && <span className="text-xs">{formatWhats(l.whatsapp)}</span>}
                    <span className="num text-xs text-muted-foreground">{l.score != null ? Math.round(Number(l.score)) : ""}</span>
                  </Link></li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <div className="mb-1.5 text-sm font-semibold">Principais pendências</div>
            {r.pendencias.length === 0 ? <p className="flex items-center gap-1.5 text-sm text-muted-foreground"><CheckCircle2 className="size-4 text-[var(--success)]" />Nenhuma.</p> :
              <ul className="space-y-1 text-sm">{r.pendencias.map((p) => <li key={p} className="flex items-start gap-1.5"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-600" />{p}</li>)}</ul>}
          </div>
        </div>
      )}
    </Secao>
  );
}

function Comparativo() {
  const [uf, setUf] = useState("SC");
  const { data } = useApi<{ numero: number; data_publicacao: string | null; leads: number; novos: number; recorrentes: number; oposicoes_apresentadas: number; quentes: number; com_contato_validado: number }[]>(`/api/rpi-semana/comparativo?uf=${uf}&limite=8`);
  return (
    <Secao titulo="Semana a semana" subtitulo="Leads novos × que já tinham aparecido" icon={CalendarClock}
      acao={<Select value={uf} onChange={setUf} options={Object.fromEntries(BRASIL_UFS.map((u) => [u.uf, u.uf]))} className="h-8 text-xs" />}>
      <div className="mb-3"><Legenda itens={[{ rotulo: "Novos", cor: SERIE(1) }, { rotulo: "Recorrentes", cor: SERIE(2) }]} /></div>
      {!data?.length ? <p className="py-6 text-center text-sm text-muted-foreground">Sem edições processadas para {NOME[uf]}.</p> : (
        <ul className="space-y-2.5">
          {data.map((e) => {
            const max = Math.max(1, ...data.map((x) => x.leads));
            return (
              <li key={e.numero} title={`RPI ${e.numero}: ${e.novos} novos, ${e.recorrentes} recorrentes, ${e.oposicoes_apresentadas} oposições apresentadas, ${e.quentes} quentes`}>
                <div className="mb-1 flex justify-between text-xs"><span><b>RPI {e.numero}</b> <span className="text-muted-foreground">{fmtDay(e.data_publicacao)}</span></span>
                  <span className="num text-muted-foreground">{e.leads} leads · {e.oposicoes_apresentadas} opos. A · {e.quentes} quentes</span></div>
                <div className="flex h-2.5 overflow-hidden rounded-full bg-muted" style={{ width: `${Math.max(6, (e.leads / max) * 100)}%` }}>
                  <div style={{ width: `${e.leads ? (e.novos / e.leads) * 100 : 0}%`, background: SERIE(1) }} />
                  <div style={{ width: `${e.leads ? (e.recorrentes / e.leads) * 100 : 0}%`, background: SERIE(2), borderLeft: e.novos && e.recorrentes ? "2px solid var(--card)" : undefined }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Secao>
  );
}

function SemanaInner() {
  const sp = useSearchParams();
  const [numero, setNumero] = useState(sp.get("numero") ?? "");
  const { data, error, reload } = useApi<Semana>(`/api/rpi-semana${numero ? `?numero=${numero}` : ""}`, 15000);
  const [msg, setMsg] = useState<string | null>(null);
  const st = data?.status;
  const acao = async (fn: () => Promise<unknown>, ok: string) => {
    setMsg(null);
    try { await fn(); setMsg(ok); reload(); } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  const terca = data?.agenda.find((a) => a.nome === "rpi-terca");

  return (
    <>
      <PageHeader title="Central RPI · Operação Semanal" description="Toda terça-feira: detecção da revista, extração, e qualificação começando por Santa Catarina. Executa no servidor, com o navegador fechado.">
        <Select value={numero} onChange={setNumero} placeholder="Edição mais recente" options={Object.fromEntries((data?.edicoes ?? []).map((e) => [String(e.numero), `RPI nº ${e.numero}`]))} />
        <Button variant="outline" onClick={() => acao(() => api("/api/rpi/discover", { method: "POST" }), "Verificação da RPI colocada na fila.")}><Radar className="size-4" /> Verificar RPI agora</Button>
        {st && <Button variant="outline" onClick={() => acao(() => api(`/api/rpi-semana/${st.edicao.numero}/priorizar`, { method: "POST" }), "Priorização refeita na fila (sem duplicar leads).")}><RefreshCw className="size-4" /> Reprocessar priorização</Button>}
      </PageHeader>
      <ErrorBox error={error} />
      {msg && <div className="mb-4 rounded-xl border bg-muted/40 p-3 text-sm">{msg}</div>}
      {st?.atraso && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-900 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          A RPI desta semana ainda não foi disponibilizada pelo INPI ({st.atraso.horas} h após terça, 14h). O sistema continua verificando a cada 10 minutos e não considera a edição publicada antes de os arquivos estarem disponíveis.
        </div>
      )}

      {data && !st && <div className="surface p-8 text-center text-sm text-muted-foreground">Nenhuma edição detectada ainda. A verificação automática roda a cada 3 h e, às terças e quartas, a cada 10 min.</div>}

      {st && (
        <div className="space-y-6">
          <section className="surface entrar overflow-hidden">
            <div className="flex flex-wrap items-center gap-4 border-b bg-[radial-gradient(120%_140%_at_0%_0%,#eef2ff,transparent_60%)] p-5 dark:bg-none">
              <div className="grid size-14 place-items-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-lg"><span className="num text-lg font-bold">{st.edicao.numero}</span></div>
              <div className="min-w-0 flex-1">
                <div className="eyebrow text-primary">Revista da Propriedade Industrial</div>
                <div className="text-lg font-semibold">RPI nº {st.edicao.numero} · publicada em {fmtDay(st.edicao.data_publicacao)}</div>
                <div className="text-xs text-muted-foreground">Detectada pelo sistema em {fmtDate(st.edicao.detectada_em)} · dados extraídos em {fmtDate(st.edicao.processada_em)} · última verificação do INPI {fmtDate(st.ultima_verificacao_rpi)}</div>
              </div>
              <div className="flex flex-col items-end gap-1 text-xs">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-violet-500/10 px-2.5 py-1 font-medium text-violet-700"><Crown className="size-3.5" />SILVANE {st.trabalhando_em ? <>trabalhando em <b>{st.trabalhando_em === "demais" ? "demais estados" : st.trabalhando_em}</b></> : "· operação concluída"}</span>
                {st.operacao?.sc_primeiros_quentes_em && <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 px-2.5 py-1 font-medium text-rose-700"><Flame className="size-3.5" />Primeiros leads quentes de SC às {new Date(st.operacao.sc_primeiros_quentes_em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</span>}
                {terca && <span className="text-muted-foreground">Monitoramento: {terca.dias_semana?.map((d) => DIAS[d]).join(" e ")} {terca.hora_inicio?.slice(0, 5)}–{terca.hora_fim?.slice(0, 5)}, a cada {terca.intervalo_minutos} min · próxima {fmtDate(terca.proximo_em)}</span>}
              </div>
            </div>
            <div className="p-5"><Linha etapas={st.etapas} /></div>
          </section>

          <Secao titulo="Andamento por estado" subtitulo="Ordem de trabalho: SC, RS, PR e depois os demais. Números reais da fila e das verificações." icon={Radar}>
            <Table>
              <TableHeader><TableRow>
                <TableHead>Estado</TableHead><TableHead className="text-right">Leads</TableHead><TableHead className="text-right">Processos</TableHead><TableHead className="text-right">Opos. A</TableHead>
                <TableHead className="text-right">Publ. B</TableHead><TableHead className="text-right">Verif. INPI</TableHead><TableHead className="text-right">Pesquisados</TableHead>
                <TableHead className="text-right">Contato validado</TableHead><TableHead className="text-right">Pend. validação</TableHead><TableHead className="text-right">Quentes</TableHead><TableHead>Agora</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {st.ufs.length === 0 && <TableRow><TableCell colSpan={11} className="py-6 text-center text-muted-foreground">Nenhum lead nesta edição.</TableCell></TableRow>}
                {st.ufs.map((u) => (
                  <TableRow key={u.uf} className={cn(u.uf === "SC" && "bg-amber-500/5")}>
                    <TableCell><Link href={`/mapa?uf=${u.uf}`} className="font-medium hover:underline">{u.uf === "PENDENTE" ? "Localização pendente" : `${u.uf} · ${NOME[u.uf]}`}</Link></TableCell>
                    <TableCell className="num text-right">{n(u.leads)}</TableCell><TableCell className="num text-right">{n(u.processos)}</TableCell>
                    <TableCell className="num text-right font-medium">{n(u.oposicoes)}</TableCell><TableCell className="num text-right">{n(u.publicados_oposicao)}</TableCell>
                    <TableCell className="num text-right">{n(u.verificados_inpi)}/{n(u.processos)}</TableCell><TableCell className="num text-right">{n(u.pesquisados)}/{n(u.leads)}</TableCell>
                    <TableCell className="num text-right">{n(u.com_contato_validado)}</TableCell><TableCell className="num text-right">{n(u.pendencias_validacao)}</TableCell>
                    <TableCell className="num text-right"><span className={cn(u.quentes && "font-semibold text-rose-600")}>{n(u.quentes)}</span></TableCell>
                    <TableCell className="text-xs">{u.falhas ? <span className="text-red-600">{u.falhas} falha(s)</span> : u.tarefas_ativas ? <span className="text-sky-700">{responsavel(u)} · {u.tarefas_ativas} na fila</span> : <span className="text-muted-foreground">{u.pesquisados >= u.leads && u.verificados_inpi >= u.processos ? "concluído" : responsavel(u)}</span>}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Secao>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <RelatorioCard numero={numero} />
            <div className="flex flex-col gap-6">
              <Comparativo />
              <Secao titulo="Execuções recentes" subtitulo="Data, hora e resultado de cada etapa automática" icon={Clock}>
                <ul className="divide-y text-xs">
                  {data.execucoes.map((j) => (
                    <li key={j.id} className="flex items-center gap-2 py-1.5">
                      <span className={cn("size-2 shrink-0 rounded-full", j.status === "succeeded" ? "bg-emerald-500" : j.status === "dead" ? "bg-red-500" : "bg-sky-500")} />
                      <span className="w-36 font-mono">{j.tipo}</span>
                      <span className="text-muted-foreground">{fmtDate(j.finalizado_em ?? j.criado_em)}</span>
                      {j.tentativas > 1 && <span className="text-amber-700">{j.tentativas} tentativas</span>}
                      <span className="min-w-0 flex-1 truncate text-red-600" title={j.erro}>{j.erro}</span>
                    </li>
                  ))}
                </ul>
                <Link href="/jobs" className="mt-2 inline-block text-xs font-medium text-primary hover:underline">Ver todos os jobs</Link>
              </Secao>
            </div>
          </div>
          {st.ufs.length > 0 && (
            <Secao titulo="Quentes por estado nesta edição" icon={Flame}>
              <BarList cor={SERIE(8)} itens={st.ufs.filter((u) => u.quentes).map((u) => ({ chave: u.uf, rotulo: NOME[u.uf], n: u.quentes }))} vazio="Ainda nenhum lead quente nesta edição." href={(uf) => `/mapa?uf=${uf}&temperatura=quente`} />
            </Secao>
          )}
          <p className="text-xs text-muted-foreground">Temperatura: <span className={cn("rounded-full px-1.5", TEMPERATURA.quente.classe)}>quente</span> oportunidade recente/relevante com contato validado · <span className={cn("rounded-full px-1.5", TEMPERATURA.morno.classe)}>morno</span> falta validação · <span className={cn("rounded-full px-1.5", TEMPERATURA.em_pesquisa.classe)}>em pesquisa</span> sem contato ou sem UF.</p>
        </div>
      )}
    </>
  );
}

export default function RpiSemanalPage() {
  return <Suspense><SemanaInner /></Suspense>;
}
