"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  AlarmClock, CheckCircle2, Download, ExternalLink, FileCheck2, Flame, Gavel, Phone, Scale, Search, ShieldAlert, Users,
} from "lucide-react";
import { KpiCard } from "@/components/kpi-card";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { Select } from "@/components/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi } from "@/components/use-api";
import { apiDownload } from "@/lib/api";
import { BRASIL_UFS } from "@/lib/brasil-geo";
import { fmtDay } from "@/lib/format";
import { CLASSE, MEDIDA, PRAZO, SERVICO, TIPO_DECISAO, textoPrazo, type Oportunidade, type Painel, type Servico } from "@/lib/servicos";
import { cn } from "@/lib/utils";

const n = (v: number | null | undefined) => Number(v ?? 0).toLocaleString("pt-BR");
const POR_PAGINA = 50;
const UFS = ["SC", "RS", "PR", ...BRASIL_UFS.map((u) => u.uf).filter((u) => !["SC", "RS", "PR"].includes(u))];
const NOME_UF = Object.fromEntries(BRASIL_UFS.map((u) => [u.uf, u.nome]));

function Abas({ servico, painel, onChange }: { servico: Servico; painel: Painel | null; onChange: (s: Servico) => void }) {
  return (
    <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2" role="tablist" aria-label="Frente comercial">
      {(Object.keys(SERVICO) as Servico[]).map((s) => {
        const d = SERVICO[s];
        const ind = painel?.[s];
        const ativo = s === servico;
        const Icone = s === "manifestacao_oposicao" ? Scale : Gavel;
        return (
          <button key={s} role="tab" aria-selected={ativo} onClick={() => onChange(s)}
            className={cn("surface lift relative overflow-hidden p-4 text-left transition", ativo ? "ring-2 ring-primary/50" : "opacity-80 hover:opacity-100")}>
            <span className="absolute inset-x-0 top-0 h-1" style={{ background: d.hex }} />
            <div className="flex items-start gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl text-white shadow-md" style={{ background: d.hex }}><Icone className="size-5" /></span>
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Pipeline {s === "manifestacao_oposicao" ? 1 : 2}</div>
                <div className="font-semibold leading-tight">{d.rotulo}</div>
                <div className="text-xs text-muted-foreground">{s === "manifestacao_oposicao" ? "Titulares cuja marca SOFREU oposição de terceiro" : "Titulares com pedido indeferido ou deferido parcialmente"}</div>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              {([["Identificadas", ind?.identificadas], ["Prazo aberto", ind?.abertas], ["Quentes", ind?.quentes]] as const).map(([k, v]) => (
                <div key={k} className="rounded-lg bg-muted/50 px-2 py-1.5"><div className="num text-lg font-semibold">{ind ? n(v) : "–"}</div><div className="text-[10px] text-muted-foreground">{k}</div></div>
              ))}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function Prazo({ o }: { o: Oportunidade }) {
  const p = PRAZO[o.prazo_status];
  return (
    <div title={o.prazo_fonte ?? undefined} className="min-w-[8.5rem]">
      <div className="num text-sm font-medium">{o.prazo_fim ? fmtDay(o.prazo_fim) : "—"}</div>
      <div className={cn("flex items-center gap-1 text-[11px]", p.classe)}>
        {o.prazo_status === "proximo_fim" && <AlarmClock className="size-3" />}{o.situacao_processual === "historico" && o.prazo_status !== "encerrado" ? p.rotulo : textoPrazo(o)}
      </div>
      {o.validacao_juridica && <div className="mt-0.5 flex items-center gap-1 text-[11px] text-orange-700 dark:text-orange-300" title={o.validacao_motivo ?? undefined}><ShieldAlert className="size-3" />validação jurídica</div>}
    </div>
  );
}

function Classe({ o }: { o: Oportunidade }) {
  const c = o.classificacao ? CLASSE[o.classificacao] : null;
  if (!c) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <span title={(o.classificacao_motivos ?? []).join("\n")} className={cn("inline-flex cursor-help items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", c.classe)}>
      {o.classificacao === "quente" ? <Flame className="size-3" /> : <span className={cn("size-1.5 rounded-full", c.ponto)} />}{c.rotulo}
    </span>
  );
}

function Pagina() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [servico, setServico] = useState<Servico>((sp.get("servico") as Servico) || "manifestacao_oposicao");
  const [uf, setUf] = useState(sp.get("uf") ?? "");
  const [cidade, setCidade] = useState("");
  const [edicao, setEdicao] = useState("");
  const [desde, setDesde] = useState("");
  const [ate, setAte] = useState("");
  const [situacao, setSituacao] = useState(sp.get("situacao") ?? "");
  const [prazo, setPrazo] = useState(sp.get("prazo") ?? "");
  const [classificacao, setClassificacao] = useState(sp.get("classificacao") ?? "");
  const [contato, setContato] = useState("");
  const [busca, setBusca] = useState("");
  const [pagina, setPagina] = useState(1);

  const pf = new URLSearchParams();
  if (uf) pf.set("uf", uf);
  if (edicao) pf.set("edicao", edicao);
  const painel = useApi<Painel>(`/api/servicos/painel?${pf}`, 60000);
  const { data: eds } = useApi<{ edicoes: { numero: number; data_publicacao: string | null }[] }>("/api/rpi-semana");

  const f = new URLSearchParams({ servico, pagina: String(pagina), por_pagina: String(POR_PAGINA) });
  for (const [k, v] of Object.entries({ uf, cidade: cidade.trim(), edicao, desde, ate, situacao, prazo, classificacao, contato, q: busca.trim() })) if (v) f.set(k, v);
  const lista = useApi<{ total: number; items: Oportunidade[] }>(`/api/servicos?${f}`, 60000);
  const ind = painel.data?.[servico];
  const set = <T,>(fn: (v: T) => void) => (v: T) => { fn(v); setPagina(1); };
  const trocar = (s: Servico) => {
    setServico(s); setPagina(1);
    const p = new URLSearchParams(sp); p.set("servico", s);
    router.replace(`${pathname}?${p}`, { scroll: false });
  };
  const exportar = (formato: string) => {
    const p = new URLSearchParams(f); p.delete("pagina"); p.delete("por_pagina"); p.delete("q"); p.delete("contato"); p.delete("desde"); p.delete("ate"); p.set("formato", formato);
    apiDownload(`/api/servicos/export?${p}`, `${servico}-${uf || "brasil"}.${formato}`);
  };
  const ehOp = servico === "manifestacao_oposicao";
  const total = lista.data?.total ?? 0;

  return (
    <>
      <PageHeader title="Oportunidades de serviço"
        description="Quem SOFREU oposição (manifestação) e quem teve o pedido indeferido (recurso). O lead é sempre o titular do pedido. Prioridade SC → RS → PR.">
        <Button variant="outline" onClick={() => exportar("xlsx")}><Download className="size-4" /> Excel</Button>
        <Button variant="outline" onClick={() => exportar("csv")}><Download className="size-4" /> CSV</Button>
      </PageHeader>
      <ErrorBox error={painel.error ?? lista.error} />
      <Abas servico={servico} painel={painel.data} onChange={trocar} />

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard rotulo={ehOp ? "Oposições sofridas" : "Indeferimentos"} valor={n(ind?.identificadas)} icon={ehOp ? Scale : Gavel} tom={ehOp ? "violet" : "blue"}
          contexto={`${n(ind?.titulares)} titular(es)${!ehOp && ind?.parciais ? ` · ${n(ind.parciais)} parcial(is)` : ""}`} />
        <KpiCard rotulo={ehOp ? "Manifestações cabíveis" : "Recursos cabíveis"} valor={n(ind?.abertas)} icon={CheckCircle2} tom="emerald" contexto="prazo aberto, sem medida" />
        <KpiCard rotulo="Já protocoladas" valor={n(ind?.protocoladas)} icon={FileCheck2} tom="slate" contexto="medida já apresentada" />
        <KpiCard rotulo="Quentes" valor={n(ind?.quentes)} icon={Flame} tom="rose" destaque contexto={`${n(ind?.mornos)} morno(s)`} href="#lista" />
        <KpiCard rotulo="Qualificados" valor={n(ind?.qualificados)} icon={Users} tom="orange" contexto="quentes + mornos" />
        <KpiCard rotulo="Contatos encontrados" valor={n(ind?.contatos_encontrados)} icon={Phone} tom="cyan" contexto="titulares com contato" />
        <KpiCard rotulo="Já abordados" valor={n(ind?.abordados)} icon={Users} tom="indigo" contexto="titulares no funil" />
        <KpiCard rotulo="Próximos do fim" valor={n(ind?.proximos_fim)} icon={AlarmClock} tom="amber"
          contexto={ind?.proximo_vencimento ? `próximo: ${fmtDay(ind.proximo_vencimento)}` : `${n(ind?.validacao_juridica)} a validar`} />
      </div>

      <div className="surface mb-4 flex flex-wrap items-end gap-3 p-3">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Estado<Select value={uf} onChange={set(setUf)} placeholder="Todos"
          options={Object.fromEntries([...UFS.map((u) => [u, `${u} · ${NOME_UF[u]}`]), ["PENDENTE", "Localização pendente"]])} /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Cidade<Input value={cidade} onChange={(e) => set(setCidade)(e.target.value)} placeholder="Município" className="w-36" /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">RPI<Select value={edicao} onChange={set(setEdicao)} placeholder="Todas"
          options={Object.fromEntries((eds?.edicoes ?? []).map((e) => [String(e.numero), `nº ${e.numero}${e.data_publicacao ? ` · ${fmtDay(e.data_publicacao)}` : ""}`]))} /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Publicada de<Input type="date" value={desde} onChange={(e) => set(setDesde)(e.target.value)} className="w-36" /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">até<Input type="date" value={ate} onChange={(e) => set(setAte)(e.target.value)} className="w-36" /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Situação<Select value={situacao} onChange={set(setSituacao)} placeholder="Todas"
          options={{ aberta: "Potencialmente cabível", historico: "Histórico", pendente: "Pendente" }} /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Prazo<Select value={prazo} onChange={set(setPrazo)} placeholder="Todos"
          options={{ em_andamento: "Em andamento", proximo_fim: "Próximo do encerramento", encerrado: "Encerrado", validacao_juridica: "Necessita validação jurídica", validar: "A validar" }} /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Prioridade<Select value={classificacao} onChange={set(setClassificacao)} placeholder="Todas"
          options={Object.fromEntries(Object.entries(CLASSE).map(([k, v]) => [k, v.rotulo]))} /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Contato<Select value={contato} onChange={set(setContato)} placeholder="Todos"
          options={{ validado: "Validado", encontrado: "Encontrado (a validar)", sem: "Sem contato" }} /></label>
        <label className="relative flex flex-col gap-1 text-xs text-muted-foreground xl:ml-auto">Buscar
          <span className="relative"><Search className="pointer-events-none absolute left-2.5 top-2.5 size-4" />
            <Input value={busca} onChange={(e) => set(setBusca)(e.target.value)} placeholder="Titular, marca, processo, CNPJ" className="w-64 pl-8" /></span></label>
      </div>

      <section id="lista" className="surface entrar overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
          <div className="text-sm font-semibold">{SERVICO[servico].rotulo} <span className="font-normal text-muted-foreground">· {n(total)} oportunidade(s) · oferta: {SERVICO[servico].oferta}</span></div>
          <div className="text-[11px] text-muted-foreground">Ordem: prioridade, estado (SC, RS, PR...), prazo mais curto</div>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Prioridade</TableHead>
                <TableHead>Processo · marca</TableHead>
                <TableHead>Titular (lead)</TableHead>
                <TableHead>{ehOp ? "Quem se opôs (informativo)" : "Decisão"}</TableHead>
                <TableHead>Prazo estimado</TableHead>
                <TableHead>{ehOp ? "Manifestação" : "Recurso"}</TableHead>
                <TableHead>Contato</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {lista.data?.items.map((o) => (
                <TableRow key={o.id} className={cn(o.situacao_processual === "historico" && "opacity-70")}>
                  <TableCell><Classe o={o} /></TableCell>
                  <TableCell>
                    <div className="num text-sm font-medium">{o.numero_processo}</div>
                    <div className="max-w-[12rem] truncate text-[11px] text-muted-foreground">{o.marca_nome ?? "marca não informada na RPI"}{o.classes_nice?.length ? ` · NCL ${o.classes_nice.join(", ")}` : ""}</div>
                    <div className="text-[11px] text-muted-foreground">RPI {o.rpi_numero} · {fmtDay(o.data_publicacao)} · {o.despacho_codigo}</div>
                  </TableCell>
                  <TableCell>
                    <div className="max-w-[16rem] truncate text-sm font-medium" title={o.titular}>{o.titular}</div>
                    <div className="text-[11px] text-muted-foreground">{o.tipo_provavel === "PJ" ? "Pessoa jurídica" : o.tipo_provavel === "PF" ? "Pessoa física" : "Tipo a confirmar"}{o.cnpj ? ` · ${o.cnpj}` : ""}</div>
                    <div className="text-[11px] text-muted-foreground" title={o.geo_status ? `localização ${o.geo_status}` : undefined}>
                      <b className="text-foreground">{o.geo_uf ?? "UF ?"}</b>{o.geo_municipio ? ` · ${o.geo_municipio}` : o.geo_status ? ` · UF ${o.geo_status}` : ""}</div>
                  </TableCell>
                  <TableCell>
                    {ehOp ? (
                      <div className="max-w-[14rem]" title={o.opositor_fonte ?? "A RPI não informa quem se opôs; aparece após a consulta das petições no pePI"}>
                        <div className="truncate text-sm">{o.opositor_nome ?? <span className="text-muted-foreground">ainda não identificado</span>}</div>
                        {o.oposicao_data && <div className="text-[11px] text-muted-foreground">oposição de {fmtDay(o.oposicao_data)}</div>}
                      </div>
                    ) : (
                      <div className="max-w-[12rem]" title={o.fundamentacao ?? undefined}>
                        <div className="text-sm">{TIPO_DECISAO[o.tipo_decisao]}</div>
                        <div className="truncate text-[11px] text-muted-foreground">{o.fundamentacao ?? "fundamentação não publicada"}</div>
                      </div>
                    )}
                  </TableCell>
                  <TableCell><Prazo o={o} /></TableCell>
                  <TableCell>
                    <div className={cn("text-xs font-medium", o.medida_status === "protocolada" ? "text-zinc-600" : o.medida_status === "nao_identificada" ? "text-emerald-700 dark:text-emerald-300" : "text-amber-700 dark:text-amber-300")}
                      title={o.medida_fonte ?? "Petições ainda não conferidas no pePI"}>{MEDIDA[o.medida_status]}</div>
                    {o.decisao_posterior && <div className="max-w-[10rem] truncate text-[11px] text-muted-foreground" title={o.decisao_posterior}>{o.decisao_posterior}</div>}
                  </TableCell>
                  <TableCell>
                    <div className="text-xs">{o.contatos_validados ? <span className="font-medium text-emerald-700 dark:text-emerald-300">{n(o.contatos_validados)} validado(s)</span> : o.contatos ? `${n(o.contatos)} a validar` : <span className="text-muted-foreground">sem contato</span>}</div>
                  </TableCell>
                  <TableCell>{o.lead_id && <Link href={`/leads/${o.lead_id}`} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">CRM<ExternalLink className="size-3" /></Link>}</TableCell>
                </TableRow>
              ))}
              {lista.data && lista.data.items.length === 0 && (
                <TableRow><TableCell colSpan={8} className="py-10 text-center text-sm text-muted-foreground">
                  Nenhuma oportunidade com estes filtros. Oportunidades aparecem depois que a RPI é lida e cruzada com o histórico.
                </TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <div className="flex items-center justify-between border-t px-4 py-2 text-xs text-muted-foreground">
          <span>Prazos: estimativa conservadora com a fonte no detalhe (passe o mouse). Abordagem só após validação humana.</span>
          <span className="flex items-center gap-2">
            <span className="num">{total ? `${(pagina - 1) * POR_PAGINA + 1}–${Math.min(pagina * POR_PAGINA, total)} de ${n(total)}` : ""}</span>
            <Button size="sm" variant="outline" disabled={pagina === 1} onClick={() => setPagina(pagina - 1)}>Anterior</Button>
            <Button size="sm" variant="outline" disabled={pagina * POR_PAGINA >= total} onClick={() => setPagina(pagina + 1)}>Próxima</Button>
          </span>
        </div>
      </section>
    </>
  );
}

export default function OportunidadesPage() {
  return <Suspense><Pagina /></Suspense>;
}
