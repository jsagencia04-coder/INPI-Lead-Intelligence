"use client";

import Link from "next/link";
import { Fragment, Suspense, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Bot, ChevronDown, ChevronRight, MessageCircle, UserRound } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { Select } from "@/components/select";
import { useApi } from "@/components/use-api";
import { api } from "@/lib/api";
import { fmtDate, fmtDay, prioridadeVariant } from "@/lib/format";
import { formatWhats } from "@/lib/whatsapp";
import type { Paged } from "@/lib/types";

type Etapa = { id: string; nome: string; automatica: boolean; leads: number; ordem: number; fase: string | null; cor: string | null; descricao: string | null; regra: string | null };
type Funil = { total: number; adicionados: number; etapas: Etapa[] };
type LeadP = { id: number; titular: string; geo_uf: string | null; pipeline_incluido_em: string | null; processos_no_pipeline: string | null; uf: string | null; prioridade: "alta" | "media" | "baixa" | null; score: number | null; whatsapp: string | null; whatsapp_status: string | null; marcas: string | null; pipeline_manual: boolean; pipeline_desde: string };
type Jornada = { etapa_pelos_fatos: string; pipeline_manual: boolean; nomes: Record<string, string>; historico: { id: number; de: string | null; para: string; origem: string; motivo: string | null; ator: string; criado_em: string }[] };

const MANUAIS = { interessado: "Interessado", reuniao: "Reunião", proposta_enviada: "Proposta enviada", negociacao: "Negociação", fechado: "Fechado", perdido: "Perdido", automatico: "Voltar à etapa automática" };
const PAGE = 50;

function JornadaLead({ id }: { id: number }) {
  const { data } = useApi<Jornada>(`/api/leads/${id}/jornada`);
  if (!data) return <p className="text-xs text-muted-foreground">Carregando…</p>;
  return (
    <div className="text-xs">
      {data.pipeline_manual && <p className="mb-2 text-muted-foreground">Etapa definida por uma pessoa. Pelos fatos gravados, o lead estaria em “{data.nomes[data.etapa_pelos_fatos]}”.</p>}
      <ol className="space-y-1">
        {data.historico.map((h) => (
          <li key={h.id} className="flex flex-wrap items-center gap-2">
            {h.origem === "manual" ? <UserRound className="size-3.5 text-sky-700" /> : <Bot className="size-3.5 text-muted-foreground" />}
            <span className="tabular-nums text-muted-foreground">{fmtDate(h.criado_em)}</span>
            <span className="font-medium">{data.nomes[h.para] ?? h.para}</span>
            {h.motivo && <span className="text-muted-foreground">· {h.motivo}</span>}
            {h.origem === "manual" && <span className="text-muted-foreground">· {h.ator.replace("user:", "")}</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function PipelineInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const leadId = sp.get("lead");
  const [soAdicionados, setSoAdicionados] = useState(sp.get("adicionados") === "1");
  const { data: funil, error, reload: recarregarFunil } = useApi<Funil>(`/api/pipeline${soAdicionados ? "?adicionados=true" : ""}`, 30000);
  const etapa = sp.get("etapa") ?? "lead_novo";
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [aberto, setAberto] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const p = new URLSearchParams({ etapa, limit: String(PAGE), offset: String(offset) });
  if (q.trim()) p.set("q", q.trim());
  if (leadId) p.set("lead_id", leadId);
  if (soAdicionados) p.set("adicionados", "true");
  const { data, reload } = useApi<Paged<LeadP>>(`/api/pipeline/leads?${p}`);
  const maior = Math.max(1, ...(funil?.etapas.map((e) => e.leads) ?? [1]));
  const atual = funil?.etapas.find((e) => e.id === etapa);

  const escolher = (id: string) => { setOffset(0); setAberto(null); router.replace(`${pathname}?etapa=${id}${soAdicionados ? "&adicionados=1" : ""}`); };
  const mover = async (lead: LeadP, destino: string) => {
    if (!destino) return;
    const motivo = window.prompt(`Motivo para mover "${lead.titular}" para "${MANUAIS[destino as keyof typeof MANUAIS]}":`);
    if (!motivo || motivo.trim().length < 3) return;
    setMsg(null);
    try {
      await api(`/api/leads/${lead.id}/pipeline`, { method: "POST", body: JSON.stringify({ etapa: destino, motivo }) });
      reload(); recarregarFunil();
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };

  return (
    <>
      <PageHeader title="Pipeline comercial" description={funil ? `${funil.total.toLocaleString("pt-BR")} lead(s) no funil · ${funil.adicionados.toLocaleString("pt-BR")} adicionado(s) pelo mapa. As etapas 1 a 10 e o opt-out seguem os fatos gravados; de “Interessado” em diante, a decisão é sua (com evidência de conversa).` : undefined}>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={soAdicionados} onChange={(e) => { setSoAdicionados(e.target.checked); setOffset(0); }} />Somente adicionados ao Pipeline</label>
      </PageHeader>
      {leadId && <div className="mb-4 flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 p-2 text-sm">Mostrando o lead nº {leadId}.<button className="ml-auto text-primary underline" onClick={() => router.replace(`${pathname}?etapa=${etapa}`)}>Ver todos da etapa</button></div>}
      <ErrorBox error={error} />
      {msg && <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">{msg}</div>}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[20rem_1fr]">
        <Card>
          <CardContent className="space-y-0.5 p-2">
            {funil?.etapas.map((e, i) => (
              <Fragment key={e.id}>
              {e.fase && e.fase !== funil.etapas[i - 1]?.fase && <div className="px-2 pb-0.5 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Fase {[...new Set(funil.etapas.map((x) => x.fase))].indexOf(e.fase) + 1} · {e.fase}</div>}
              <button onClick={() => escolher(e.id)} title={[e.descricao, e.regra].filter(Boolean).join(" · ")}
                className={`relative flex w-full items-center gap-2 overflow-hidden rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent ${etapa === e.id ? "bg-accent font-medium" : ""}`}>
                <span className="absolute inset-y-0 left-0 bg-primary/10" style={{ width: `${(e.leads / maior) * 100}%` }} />
                <span className="relative size-2 rounded-full" style={{ background: e.cor ?? "#94a3b8" }} />
                <span className="relative w-5 text-right text-xs tabular-nums text-muted-foreground">{e.ordem}</span>
                <span className="relative flex-1 truncate">{e.nome}</span>
                {!e.automatica && <UserRound className="relative size-3 text-muted-foreground" aria-label="Etapa decidida por pessoa" />}
                <span className="relative tabular-nums">{e.leads.toLocaleString("pt-BR")}</span>
              </button>
              </Fragment>
            ))}
          </CardContent>
        </Card>
        <Card className="min-w-0">
          <CardContent className="overflow-x-auto">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">{atual ? `${atual.ordem}. ${atual.nome}` : ""}</h2>
              {atual?.descricao && <span className="text-xs text-muted-foreground">{atual.descricao}</span>}
              <Input placeholder="Titular ou CNPJ" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} className="ml-auto w-64" />
            </div>
            <Table>
              <TableHeader><TableRow><TableHead className="w-6" /><TableHead>Titular</TableHead><TableHead>Marca</TableHead><TableHead>WhatsApp</TableHead><TableHead>Nesta etapa desde</TableHead><TableHead>Mover para</TableHead></TableRow></TableHeader>
              <TableBody>
                {data?.items.length === 0 && <TableRow><TableCell colSpan={6} className="text-muted-foreground">Nenhum lead nesta etapa.</TableCell></TableRow>}
                {data?.items.map((l) => (
                  <Fragment key={l.id}>
                    <TableRow>
                      <TableCell>
                        <button onClick={() => setAberto(aberto === l.id ? null : l.id)} aria-label="Ver a jornada" className="rounded p-1 hover:bg-accent">
                          {aberto === l.id ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                        </button>
                      </TableCell>
                      <TableCell className="max-w-64">
                        <Link href={`/leads/${l.id}`} className="block truncate font-medium underline-offset-4 hover:underline" title={l.titular}>{l.titular}</Link>
                        <div className="flex items-center gap-1 text-xs text-muted-foreground">
                          {l.prioridade && <Badge variant={prioridadeVariant[l.prioridade]}>{l.prioridade}</Badge>}{l.uf ?? ""}
                          {l.pipeline_manual && <span title="Etapa definida por uma pessoa" className="inline-flex items-center gap-0.5"><UserRound className="size-3" /> manual</span>}
                          {l.processos_no_pipeline && <span title={`Processo(s) adicionado(s): ${l.processos_no_pipeline}`} className="font-mono">· {l.processos_no_pipeline}</span>}
                        </div>
                      </TableCell>
                      <TableCell className="max-w-40 truncate text-sm" title={l.marcas ?? ""}>{l.marcas ?? "—"}</TableCell>
                      <TableCell className="whitespace-nowrap text-sm">
                        {l.whatsapp ? <span className="inline-flex items-center gap-1"><MessageCircle className={`size-3.5 ${l.whatsapp_status === "candidato" ? "text-amber-500" : "text-[#25D366]"}`} />{formatWhats(l.whatsapp)}</span> : "—"}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs">{fmtDay(l.pipeline_desde)}</TableCell>
                      <TableCell>{etapa !== "opt_out" && <Select value="" onChange={(v) => mover(l, v)} placeholder="Escolher…" options={MANUAIS} className="h-8 text-xs" />}</TableCell>
                    </TableRow>
                    {aberto === l.id && <TableRow><TableCell colSpan={6} className="bg-muted/30"><JornadaLead id={l.id} /></TableCell></TableRow>}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
            {data && data.total > PAGE && (
              <div className="mt-4 flex items-center justify-end gap-2 text-sm">
                <span className="text-muted-foreground">{offset + 1}–{Math.min(offset + PAGE, data.total)} de {data.total.toLocaleString("pt-BR")}</span>
                <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>Anterior</Button>
                <Button size="sm" variant="outline" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Próxima</Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

export default function PipelinePage() {
  return <Suspense><PipelineInner /></Suspense>;
}
