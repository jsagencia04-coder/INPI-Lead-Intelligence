"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Download, MessageCircle } from "lucide-react";
import { formatWhats } from "@/components/whatsapp-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { Select } from "@/components/select";
import { useApi } from "@/components/use-api";
import { apiDownload } from "@/lib/api";
import { categoriaLabel, diasAte, fmtDay, leadStatusLabel, prioridadeVariant } from "@/lib/format";
import type { LeadListItem, Paged } from "@/lib/types";

const PAGE = 50;

function LeadsInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const setParam = (k: string, v: string) => {
    const p = new URLSearchParams(sp);
    if (v) p.set(k, v);
    else p.delete(k);
    setOffset(0);
    router.replace(`${pathname}?${p}`);
  };
  const filtros = new URLSearchParams();
  for (const k of ["status", "prioridade", "categoria", "revisao", "whatsapp"]) if (sp.get(k)) filtros.set(k, sp.get(k)!);
  const params = new URLSearchParams(filtros);
  if (q.trim()) params.set("q", q.trim());
  params.set("limit", String(PAGE));
  params.set("offset", String(offset));
  const { data, error } = useApi<Paged<LeadListItem>>(`/api/leads?${params}`);

  const exportar = (formato: string) => {
    const p = new URLSearchParams(filtros);
    p.delete("revisao");
    p.set("formato", formato);
    apiDownload(`/api/leads-export?${p}`, `leads.${formato}`);
  };

  return (
    <>
      <PageHeader title="Leads" description={data ? `${data.total.toLocaleString("pt-BR")} lead(s). Um por titular, ordenados por prioridade.` : undefined}>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => exportar("xlsx")}><Download className="size-4" /> Excel</Button>
          <Button variant="outline" onClick={() => exportar("csv")}><Download className="size-4" /> CSV</Button>
        </div>
      </PageHeader>
      <div className="mb-4 flex flex-wrap gap-2">
        <Input placeholder="Titular, CNPJ, marca ou processo" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} className="w-72" />
        <Select value={sp.get("prioridade") ?? ""} onChange={(v) => setParam("prioridade", v)} placeholder="Todas as prioridades"
          options={{ alta: "Alta", media: "Média", baixa: "Baixa" }} />
        <Select value={sp.get("status") ?? ""} onChange={(v) => setParam("status", v)} placeholder="Todos os status" options={leadStatusLabel} />
        <Select value={sp.get("categoria") ?? ""} onChange={(v) => setParam("categoria", v)} placeholder="Todas as categorias"
          options={Object.fromEntries(Object.entries(categoriaLabel).filter(([k]) => !["outro", "arquivamento"].includes(k)))} />
        <Select value={sp.get("whatsapp") ?? ""} onChange={(v) => setParam("whatsapp", v)} placeholder="WhatsApp: todos"
          options={{ validado: "WhatsApp validado", candidato: "WhatsApp candidato", nenhum: "Sem WhatsApp" }} />
        <Select value={sp.get("revisao") ?? ""} onChange={(v) => setParam("revisao", v)} placeholder="Revisão: todos"
          options={{ true: "Precisa revisão", false: "Revisados" }} />
      </div>
      <ErrorBox error={error} />
      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Prioridade</TableHead><TableHead>Titular</TableHead><TableHead>WhatsApp</TableHead><TableHead>Categoria</TableHead>
                <TableHead>Prazo estimado</TableHead><TableHead className="text-right">Proc.</TableHead>
                <TableHead>Contatos</TableHead><TableHead>Procurador</TableHead><TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.items.length === 0 && (
                <TableRow><TableCell colSpan={9} className="text-muted-foreground">
                  Nenhum lead. Os leads são montados após a importação da RPI (agente leads.build, a cada hora).
                </TableCell></TableRow>
              )}
              {data?.items.map((l) => {
                const dias = diasAte(l.prazo_ate);
                return (
                  <TableRow key={l.id}>
                    <TableCell>
                      {l.prioridade && <Badge variant={prioridadeVariant[l.prioridade]}>{l.prioridade}</Badge>}
                      <span className="ml-2 text-xs tabular-nums text-muted-foreground">{l.score ?? ""}</span>
                    </TableCell>
                    <TableCell className="max-w-64">
                      <Link href={`/leads/${l.id}`} className="block truncate font-medium underline-offset-4 hover:underline" title={l.titular}>{l.titular}</Link>
                      <div className="text-xs text-muted-foreground">
                        {l.tipo_provavel} · {l.uf ?? "UF ?"}{l.cnpj ? ` · CNPJ ${l.cnpj}` : l.cnpj_status === "ambiguo" ? " · CNPJ ambíguo" : ""}
                        {l.segmento ? ` · ${l.segmento}` : ""}
                      </div>
                    </TableCell>
                    <TableCell>
                      {l.whatsapp ? (
                        <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-sm">
                          <MessageCircle className={`size-4 ${l.whatsapp_status === "candidato" ? "text-amber-500" : "text-[#25D366]"}`} />
                          {formatWhats(l.whatsapp)}
                          <span className={`text-[10px] ${l.whatsapp_status === "candidato" ? "text-amber-700" : "text-emerald-700"}`}>
                            {l.whatsapp_status === "confirmado" ? "confirmado" : l.whatsapp_status === "validado" ? "validado" : "candidato"}</span>
                        </span>
                      ) : <span className="text-xs text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell>{l.categoria_principal ? categoriaLabel[l.categoria_principal] : "—"}</TableCell>
                    <TableCell className={dias !== null && dias <= 15 ? "font-medium text-destructive" : ""}>
                      {fmtDay(l.prazo_ate)}{dias !== null && <span className="ml-1 text-xs">({dias}d)</span>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{l.n_processos}</TableCell>
                    <TableCell className="text-xs">{l.n_validados} validado(s) / {l.n_contatos}</TableCell>
                    <TableCell className="text-xs">{l.procurador_confirmado ? "Sem (INPI)" : "Sem (só RPI)"}</TableCell>
                    <TableCell>
                      <span className="text-sm">{leadStatusLabel[l.status] ?? l.status}</span>
                      {l.precisa_revisao && <Badge variant="outline" className="ml-1">revisar</Badge>}
                    </TableCell>
                  </TableRow>
                );
              })}
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
    </>
  );
}

export default function LeadsPage() {
  return <Suspense><LeadsInner /></Suspense>;
}
