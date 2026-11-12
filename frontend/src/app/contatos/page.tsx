"use client";

import Link from "next/link";
import { Fragment, Suspense, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Ban, ChevronDown, ChevronRight, Download, ExternalLink, MessageCircle, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Consentimento } from "@/components/consentimento";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { Select } from "@/components/select";
import { useApi } from "@/components/use-api";
import { apiDownload } from "@/lib/api";
import { FILTROS, ORDENS, WA_NIVEL, fmtCnpj, melhor, origem, quantos, statusContato, type ContatoCentral, type TitularCentral } from "@/lib/contatos";
import { fmtDay, leadStatusLabel } from "@/lib/format";
import { formatWhats } from "@/lib/whatsapp";
import type { Paged } from "@/lib/types";

const PAGE = 50;
const COLUNAS = ["whatsapp", "telefone", "email", "site", "instagram", "linkedin"] as const;

function mostra(c: ContatoCentral) {
  if (c.tipo === "whatsapp" || c.tipo === "telefone") return formatWhats(c.valor_normalizado);
  if (c.tipo === "instagram" || c.tipo === "linkedin") return "@" + c.valor_normalizado.split("/").pop();
  return c.valor_normalizado;
}

function Fonte({ c }: { c: ContatoCentral }) {
  const o = origem(c);
  return o.href
    ? <a href={o.href} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-0.5 underline-offset-2 hover:underline" title="Abrir a fonte original">{o.texto}<ExternalLink className="size-3" /></a>
    : <span>{o.texto}</span>;
}

function Celula({ t, tipo }: { t: TitularCentral; tipo: string }) {
  const c = melhor(t.contatos, tipo);
  if (!c) return <span className="text-xs text-muted-foreground">—</span>;
  const extra = quantos(t.contatos, tipo) - 1;
  const cor = c.tipo === "whatsapp" && c.wa_nivel ? WA_NIVEL[c.wa_nivel].cor : c.verificacao === "dominio_ok" || c.verificacao === "verificado_humano" ? "text-emerald-700" : "text-muted-foreground";
  return (
    <div className="max-w-48 text-xs leading-tight">
      <div className="flex items-center gap-1 truncate text-sm" title={c.valor}>
        {tipo === "whatsapp" && <MessageCircle className={`size-3.5 shrink-0 ${c.wa_nivel === "company_evidence" || c.wa_nivel === "human_confirmed" ? "text-[#25D366]" : "text-amber-500"}`} />}
        <span className="truncate">{mostra(c)}</span>
        {c.com_permissao && <ShieldCheck className="size-3.5 shrink-0 text-emerald-600" aria-label="Com permissão de comunicação" />}
        {c.bloqueado && <Ban className="size-3.5 shrink-0 text-destructive" aria-label="Bloqueado (opt-out)" />}
      </div>
      <div className={cor} title={c.tipo === "whatsapp" && c.wa_nivel ? WA_NIVEL[c.wa_nivel].dica : undefined}>{statusContato(c)}{extra > 0 ? ` · +${extra}` : ""}</div>
      <div className="truncate text-muted-foreground"><Fonte c={c} /></div>
    </div>
  );
}

function Detalhe({ t }: { t: TitularCentral }) {
  const [autorizacao, setAutorizacao] = useState<number | null>(null);
  const emails = t.contatos.filter((c) => c.tipo === "email" && c.verificacao !== "invalido" && !c.bloqueado);
  if (t.contatos.length === 0) return <p className="text-sm text-muted-foreground">Nenhum contato encontrado para este titular até agora.</p>;
  return (
    <table className="w-full text-xs">
      <thead className="text-left text-muted-foreground">
        <tr><th className="py-1 pr-3">Tipo</th><th className="pr-3">Contato</th><th className="pr-3">Status</th><th className="pr-3">Confiança</th><th className="pr-3">Origem</th><th className="pr-3">Encontrado em</th><th>Trecho da fonte</th></tr>
      </thead>
      <tbody>
        {t.contatos.map((c) => (
          <Fragment key={c.id}>
          <tr className={`border-t align-top ${c.verificacao === "invalido" ? "opacity-60" : ""}`}>
            <td className="py-1.5 pr-3 font-medium">{c.tipo}</td>
            <td className="pr-3">{c.valor}</td>
            <td className="pr-3">
              {statusContato(c)}
              {c.tipo === "whatsapp" && <div className="text-muted-foreground">conta: {c.wa_conta} · comercial: {c.wa_comercial.replaceAll("_", " ")}</div>}
              {c.tipo === "telefone" && c.eh_celular !== null && <div className="text-muted-foreground">{c.eh_celular ? "celular" : "fixo"}</div>}
              <div className={c.com_permissao ? "text-emerald-700" : "text-muted-foreground"}>{c.com_permissao ? "com autorização registrada" : "sem autorização"}</div>
              {c.bloqueado && <div className="text-destructive">bloqueado (opt-out)</div>}
              {c.tipo === "whatsapp" && c.verificacao !== "invalido" && (
                <button className="mt-1 underline underline-offset-2" onClick={() => setAutorizacao(autorizacao === c.id ? null : c.id)}>
                  {autorizacao === c.id ? "Fechar" : "Autorização e elegibilidade"}
                </button>
              )}
            </td>
            <td className="pr-3 tabular-nums">{c.confianca !== null ? `${Math.round(c.confianca * 100)}%` : "—"}</td>
            <td className="max-w-56 truncate pr-3"><Fonte c={c} /></td>
            <td className="pr-3 whitespace-nowrap">{fmtDay(c.fonte_obtida_em ?? c.created_at)}</td>
            <td className="max-w-80 text-muted-foreground">{c.fonte_trecho ? `“${c.fonte_trecho.slice(0, 160)}”` : c.observacao ?? "—"}</td>
          </tr>
          {autorizacao === c.id && <tr><td colSpan={7}><Consentimento contato={c} emails={emails} /></td></tr>}
          </Fragment>
        ))}
      </tbody>
    </table>
  );
}

function ContatosInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [aberto, setAberto] = useState<number | null>(null);
  const filtro = sp.get("filtro") ?? "todos";
  const ordenar = sp.get("ordenar") ?? "titular";
  const direcao = sp.get("direcao") ?? (ordenar === "titular" ? "asc" : "desc");
  const setParam = (k: string, v: string) => {
    const p = new URLSearchParams(sp);
    if (v) p.set(k, v); else p.delete(k);
    if (k === "ordenar") p.delete("direcao");
    setOffset(0);
    router.replace(`${pathname}?${p}`);
  };
  const base = new URLSearchParams({ filtro });
  if (q.trim()) base.set("q", q.trim());
  const params = new URLSearchParams(base);
  params.set("ordenar", ordenar); params.set("direcao", direcao);
  params.set("limit", String(PAGE)); params.set("offset", String(offset));
  const { data, error } = useApi<Paged<TitularCentral>>(`/api/contact-central?${params}`);
  const { data: cont } = useApi<Record<string, number>>("/api/contact-central/counts");

  const exportar = (formato: string) => {
    const p = new URLSearchParams(base);
    p.set("formato", formato);
    apiDownload(`/api/contact-central/export?${p}`, `contatos.${formato}`);
  };

  return (
    <>
      <PageHeader title="Central de contatos" description={data ? `${data.total.toLocaleString("pt-BR")} titular(es) neste filtro. Cada contato aparece uma única vez, com a origem.` : undefined}>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => exportar("xlsx")}><Download className="size-4" /> Excel</Button>
          <Button variant="outline" onClick={() => exportar("csv")}><Download className="size-4" /> CSV</Button>
        </div>
      </PageHeader>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {Object.entries(FILTROS).map(([k, rotulo]) => (
          <button key={k} onClick={() => setParam("filtro", k === "todos" ? "" : k)}
            className={`rounded-full border px-3 py-1 text-xs transition-colors ${filtro === k ? "border-primary bg-primary text-primary-foreground" : "bg-background hover:bg-accent"}`}>
            {rotulo}{cont ? <span className="ml-1.5 tabular-nums opacity-70">{cont[k]?.toLocaleString("pt-BR")}</span> : null}
          </button>
        ))}
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        <Input placeholder="Nome, CNPJ, marca ou nº do processo" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} className="w-80" />
        <Select value={ordenar} onChange={(v) => setParam("ordenar", v)} options={ORDENS} />
        <Select value={direcao} onChange={(v) => setParam("direcao", v)} options={{ asc: "Crescente", desc: "Decrescente" }} />
      </div>
      <ErrorBox error={error} />
      <Card>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-6" /><TableHead>Titular</TableHead><TableHead>Marca / processo</TableHead>
                <TableHead>WhatsApp</TableHead><TableHead>Telefone</TableHead><TableHead>E-mail</TableHead>
                <TableHead>Site</TableHead><TableHead>Instagram</TableHead><TableHead>LinkedIn</TableHead><TableHead>Pesquisa</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.items.length === 0 && (
                <TableRow><TableCell colSpan={10} className="text-muted-foreground">Nenhum titular neste filtro.</TableCell></TableRow>
              )}
              {data?.items.map((t) => (
                <Fragment key={t.holder_id}>
                  <TableRow className="align-top">
                    <TableCell>
                      <button onClick={() => setAberto(aberto === t.holder_id ? null : t.holder_id)} aria-label="Ver todos os contatos e fontes" className="rounded p-1 hover:bg-accent">
                        {aberto === t.holder_id ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                      </button>
                    </TableCell>
                    <TableCell className="max-w-64">
                      {t.lead_id
                        ? <Link href={`/leads/${t.lead_id}`} className="block truncate font-medium underline-offset-4 hover:underline" title={t.titular}>{t.titular}</Link>
                        : <span className="block truncate font-medium" title={t.titular}>{t.titular}</span>}
                      <div className="text-xs leading-tight text-muted-foreground">
                        {t.razao_social && t.razao_social !== t.titular && <div className="truncate" title={t.razao_social}>Razão social: {t.razao_social}</div>}
                        {t.nome_fantasia && <div className="truncate">Fantasia: {t.nome_fantasia}</div>}
                        <div>{t.cnpj ? `CNPJ ${fmtCnpj(t.cnpj)}` : t.cnpj_status === "ambiguo" ? "CNPJ ambíguo (homônimos)" : "CNPJ não identificado"}{t.uf ? ` · ${t.uf}` : ""}</div>
                        <div className="mt-0.5 flex flex-wrap gap-1">
                          {t.lead_status && <Badge variant="outline">{leadStatusLabel[t.lead_status] ?? t.lead_status}</Badge>}
                          {(t.titular_bloqueado || t.n_bloqueados > 0) && <Badge variant="destructive">bloqueado</Badge>}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="max-w-44 text-xs">
                      <div className="truncate text-sm" title={t.marcas ?? ""}>{t.marcas ?? "—"}</div>
                      <div className="truncate text-muted-foreground" title={t.processos ?? ""}>{t.processos ?? ""}</div>
                    </TableCell>
                    {COLUNAS.map((tipo) => <TableCell key={tipo}><Celula t={t} tipo={tipo} /></TableCell>)}
                    <TableCell className="whitespace-nowrap text-xs">{fmtDay(t.pesquisado_em)}</TableCell>
                  </TableRow>
                  {aberto === t.holder_id && (
                    <TableRow><TableCell colSpan={10} className="bg-muted/30"><Detalhe t={t} /></TableCell></TableRow>
                  )}
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
      <p className="mt-3 text-xs text-muted-foreground">
        Celular, conta de WhatsApp, WhatsApp comercial e autorização são informações separadas. Um número público não é consentimento:
        “com permissão” só aparece quando há autorização registrada. Telefone da Receita nunca vira WhatsApp validado sozinho.
      </p>
    </>
  );
}

export default function ContatosPage() {
  return <Suspense><ContatosInner /></Suspense>;
}
