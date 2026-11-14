"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, ListOrdered, Plus } from "lucide-react";
import { AdicionarPipeline, linkPipeline } from "@/components/adicionar-pipeline";
import { Secao } from "@/components/kpi-card";
import { ErrorBox } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi } from "@/components/use-api";
import { PRIORIDADE, PROCURADOR, UFS_SUL, type IndicadoresComerciais, type OportunidadeOp } from "@/lib/comercial";
import { fmtDay } from "@/lib/format";
import { cn } from "@/lib/utils";

const n = (v: number | null | undefined) => Number(v ?? 0).toLocaleString("pt-BR");
const PAGE = 25;

function Chips<T extends string>({ valor, opcoes, onChange, rotulo }: { valor: T; opcoes: [T, string][]; onChange: (v: T) => void; rotulo: string }) {
  return (
    <div className="flex items-center gap-1" role="radiogroup" aria-label={rotulo}>
      {opcoes.map(([k, r]) => (
        <button key={k} role="radio" aria-checked={valor === k} onClick={() => onChange(k)}
          className={cn("rounded-full border px-2.5 py-1 text-xs", valor === k ? "border-primary bg-primary/10 font-medium text-primary" : "hover:bg-accent")}>{r}</button>
      ))}
    </div>
  );
}

/** V2.6 · Indicadores da coleta e comparativo SC × RS × PR (mesma base da lista operacional). */
export function IndicadoresColeta() {
  const { data: d } = useApi<IndicadoresComerciais>("/api/comercial/indicadores", 120000);
  if (!d) return null;
  const alertas = d.edicoes.filter((e) => e.alerta);
  const max = Math.max(1, ...d.sul.map((s) => s.oposicoes + s.indeferimentos));
  return (
    <div className="surface mb-4 grid gap-4 p-4 lg:grid-cols-[1.2fr_1fr]">
      <div>
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold">Operação a partir da RPI {d.edicao_minima}
          <span className="text-xs font-normal text-muted-foreground">{d.rpis_processadas} edição(ões) processada(s)</span></div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {([["Oposições", d.oportunidades.oposicoes, "text-rose-700"], ["Indeferimentos", d.oportunidades.indeferimentos, "text-amber-700"],
            ["Sem procurador confirmado", d.representacao.SEM_PROCURADOR_CONFIRMADO, "text-emerald-700"], ["Com procurador", d.representacao.COM_PROCURADOR, ""],
            ["Representação desconhecida", d.representacao.PROCURADOR_DESCONHECIDO + d.representacao.ERRO_NA_IDENTIFICACAO, ""], ["Leads no Pipeline", d.leads.no_pipeline, ""],
            ["Com autorização", d.leads.com_autorizacao, ""], ["Elegíveis 1º contato", d.leads.elegiveis_primeiro_contato, ""]] as const).map(([k, v, c]) => (
            <div key={k} className="rounded-lg border p-2"><div className="text-[11px] text-muted-foreground">{k}</div><div className={cn("num text-lg font-semibold", c)}>{n(v)}</div></div>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">Oposições e indeferimentos contam só oportunidades elegíveis (sem procurador confirmado). Prioridade comercial não é autorização de envio.</p>
        {alertas.map((e) => (
          <p key={e.numero} className="mt-2 flex gap-1.5 rounded-md bg-amber-500/10 p-2 text-xs text-amber-900"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />RPI {e.numero}: {e.alerta}</p>
        ))}
        {alertas.length === 0 && d.edicoes.length > 0 && <p className="mt-2 flex items-center gap-1.5 text-xs text-emerald-700"><CheckCircle2 className="size-3.5" />Todas as edições operacionais lidas por inteiro, sem divergência.</p>}
      </div>
      <div>
        <div className="mb-2 text-sm font-semibold">SC × RS × PR</div>
        <ul className="space-y-2">{d.sul.map((s) => (
          <li key={s.uf} className="text-xs">
            <div className="mb-0.5 flex justify-between"><span className="font-medium">{s.ordem}º · {s.uf}</span><span className="text-muted-foreground">{n(s.oposicoes)} oposição(ões) · {n(s.indeferimentos)} indeferimento(s) · {n(s.no_pipeline)} no pipeline</span></div>
            <div className="flex h-2 overflow-hidden rounded-full bg-muted">
              <div className="bg-rose-500" style={{ width: `${(s.oposicoes / max) * 100}%` }} />
              <div className="bg-amber-400" style={{ width: `${(s.indeferimentos / max) * 100}%` }} />
            </div>
          </li>
        ))}</ul>
        <p className="mt-2 text-[11px] text-muted-foreground">Sem UF identificada (separados, sem prioridade): {n(d.sem_uf.oposicoes)} oposição(ões) · {n(d.sem_uf.indeferimentos)} indeferimento(s).</p>
      </div>
    </div>
  );
}

/** V2.6 · Lista operacional por processo: oposição antes de indeferimento; depois SC, RS, PR, demais e sem UF. */
export function OportunidadesPriorizadas({ edicao }: { edicao?: string }) {
  const [uf, setUf] = useState<"" | "SC" | "RS" | "PR">("");
  const [servico, setServico] = useState<"" | "manifestacao_oposicao" | "recurso_indeferimento">("");
  const [pagina, setPagina] = useState(1);
  const [aberto, setAberto] = useState<string | null>(null);
  const q = new URLSearchParams({ pagina: String(pagina), por_pagina: String(PAGE) });
  if (uf) q.set("uf", uf);
  if (servico) q.set("servico", servico);
  if (edicao) q.set("edicao", edicao);
  const { data, error, reload } = useApi<{ total: number; items: OportunidadeOp[] }>(`/api/servicos?${q}`);
  return (
    <Secao className="mt-6" titulo="Oportunidades priorizadas por processo" icon={ListOrdered}
      subtitulo={data ? `${n(data.total)} processo(s) sem procurador confirmado · oposição → indeferimento · SC → RS → PR` : undefined}
      acao={<div className="flex flex-wrap gap-3">
        <Chips rotulo="Estado" valor={uf} onChange={(v) => { setUf(v); setPagina(1); }} opcoes={[["", "Todos"], ...UFS_SUL.map((u) => [u, u] as ["SC" | "RS" | "PR", string])]} />
        <Chips rotulo="Despacho" valor={servico} onChange={(v) => { setServico(v); setPagina(1); }}
          opcoes={[["", "Todos"], ["manifestacao_oposicao", "Oposições"], ["recurso_indeferimento", "Indeferimentos"]]} />
      </div>}>
      <ErrorBox error={error} />
      <Table>
        <TableHeader><TableRow>
          <TableHead>Prioridade</TableHead><TableHead>UF</TableHead><TableHead>Processo / marca</TableHead><TableHead>Titular</TableHead>
          <TableHead>RPI</TableHead><TableHead>Prazo</TableHead><TableHead>Procurador</TableHead><TableHead>Contatos</TableHead><TableHead className="text-right">Gestão comercial</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {data?.items.length === 0 && <TableRow><TableCell colSpan={9} className="py-8 text-center text-muted-foreground">Nenhuma oportunidade com esses filtros.</TableCell></TableRow>}
          {data?.items.map((o) => (
            <TableRow key={o.id} className="align-top">
              <TableCell><span className={cn("whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium", PRIORIDADE[o.prioridade]?.classe)}>{PRIORIDADE[o.prioridade]?.rotulo}</span></TableCell>
              <TableCell className="text-xs">{o.geo_uf ?? <span className="text-amber-700">Sem UF</span>}</TableCell>
              <TableCell className="text-xs"><span className="font-mono">{o.numero_processo}</span><span className="block max-w-48 truncate text-muted-foreground" title={o.marca_nome ?? ""}>{o.marca_nome ?? "—"}</span></TableCell>
              <TableCell className="max-w-56 truncate text-xs" title={o.titular}>{o.lead_id ? <Link href={`/leads/${o.lead_id}`} className="hover:underline">{o.titular}</Link> : o.titular}</TableCell>
              <TableCell className="whitespace-nowrap text-xs">{o.rpi_numero}<span className="block text-muted-foreground">{fmtDay(o.data_publicacao)}</span></TableCell>
              <TableCell className="whitespace-nowrap text-xs">{fmtDay(o.prazo_fim)}</TableCell>
              <TableCell className="text-xs">{PROCURADOR[o.procurador_situacao]?.rotulo ?? o.procurador_situacao}</TableCell>
              <TableCell className="text-xs">{o.contatos_validados} de {o.contatos}</TableCell>
              <TableCell className="text-right">
                {o.no_pipeline && o.lead_id
                  ? <Link href={linkPipeline(o.lead_id, o.pipeline_stage ?? "lead_novo")} className="text-xs font-medium text-primary hover:underline">No pipeline</Link>
                  : <Button size="sm" variant="outline" onClick={() => setAberto(o.numero_processo)}><Plus className="size-3.5" />Pipeline</Button>}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {data && data.total > PAGE && (
        <div className="mt-4 flex items-center justify-end gap-2 text-sm">
          <span className="text-muted-foreground">{(pagina - 1) * PAGE + 1}–{Math.min(pagina * PAGE, data.total)} de {n(data.total)}</span>
          <Button size="sm" variant="outline" disabled={pagina === 1} onClick={() => setPagina(pagina - 1)}>Anterior</Button>
          <Button size="sm" variant="outline" disabled={pagina * PAGE >= data.total} onClick={() => setPagina(pagina + 1)}>Próxima</Button>
        </div>
      )}
      {aberto && <AdicionarPipeline numero={aberto} onFechar={() => setAberto(null)} onFeito={reload} />}
    </Secao>
  );
}

/** V2.6 · Relatório de execução de cada RPI operacional (completude, oposições, indeferimentos, representação). */
export function AuditoriaRpi() {
  const { data: d } = useApi<IndicadoresComerciais>("/api/comercial/indicadores", 120000);
  if (!d) return null;
  const v = (a: Record<string, unknown>, k: string) => (a[k] == null ? "—" : n(Number(a[k])));
  return (
    <Secao className="mb-6" titulo={`Auditoria da coleta · edições a partir da ${d.edicao_minima}`} icon={ListOrdered}
      subtitulo="Edições anteriores ficam só no histórico: não entram em coleta, mapa, indicadores nem pipeline.">
      <Table>
        <TableHeader><TableRow>
          <TableHead>RPI</TableHead><TableHead>Situação</TableHead><TableHead className="text-right">Processos lidos</TableHead>
          <TableHead className="text-right">Oposições (XML / gravadas)</TableHead><TableHead className="text-right">Indeferimentos (XML / gravados)</TableHead>
          <TableHead className="text-right">Com procurador</TableHead><TableHead className="text-right">Sem procurador conf.</TableHead>
          <TableHead className="text-right">Desconhecida / erro</TableHead><TableHead className="text-right">Duplicidades</TableHead><TableHead className="text-right">Tempo</TableHead>
        </TableRow></TableHeader>
        <TableBody>{d.edicoes.map((e) => { const a = e.auditoria ?? {}; return (
          <TableRow key={e.numero} className="align-top">
            <TableCell className="whitespace-nowrap">{e.numero}<span className="block text-xs text-muted-foreground">{fmtDay(e.data_publicacao)}</span></TableCell>
            <TableCell className="max-w-72 text-xs">{e.completa ? <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle2 className="size-3.5" />Completa</span>
              : <span className="inline-flex gap-1 text-amber-800"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{e.alerta ?? "Incompleta"}</span>}</TableCell>
            <TableCell className="num text-right">{v(a, "processos_lidos")}</TableCell>
            <TableCell className="num text-right">{v(a, "oposicoes_encontradas")} / {v(a, "oposicoes_gravadas")}</TableCell>
            <TableCell className="num text-right">{v(a, "indeferimentos_encontrados")} / {v(a, "indeferimentos_gravados")}</TableCell>
            <TableCell className="num text-right">{v(a, "com_procurador")}</TableCell>
            <TableCell className="num text-right">{v(a, "sem_procurador_confirmado")}</TableCell>
            <TableCell className="num text-right">{v(a, "representacao_desconhecida")} / {v(a, "erros_identificacao_procurador")}</TableCell>
            <TableCell className="num text-right">{v(a, "duplicidades_no_xml")}</TableCell>
            <TableCell className="num text-right">{a.tempo_segundos == null ? "—" : `${a.tempo_segundos}s`}</TableCell>
          </TableRow>); })}</TableBody>
      </Table>
    </Secao>
  );
}
