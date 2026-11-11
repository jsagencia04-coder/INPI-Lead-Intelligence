"use client";

import Link from "next/link";
import { useState } from "react";
import { Download, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { useApi } from "@/components/use-api";
import { api, apiDownload } from "@/lib/api";
import { categoriaLabel, fmtDate, fmtDay, fmtNum, leadStatusLabel, prioridadeVariant } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function RelatoriosPage() {
  const lista = useApi<any[]>("/api/reports");
  const [sel, setSel] = useState<number | null>(null);
  const preview = useApi<any>(sel ? null : "/api/reports/preview");
  const salvo = useApi<any>(sel ? `/api/reports/${sel}` : null);
  const d = sel ? salvo.data?.dados : preview.data;
  const [msg, setMsg] = useState<string | null>(null);

  return (
    <>
      <PageHeader title="Relatórios" description="Relatório semanal por edição da RPI. Gerado automaticamente todo dia; pode ser gerado agora.">
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => apiDownload("/api/leads-export?formato=xlsx", "leads.xlsx")}><Download className="size-4" /> Leads (Excel)</Button>
          <Button onClick={async () => { await api("/api/reports", { method: "POST" }); setMsg("Relatório enfileirado."); setTimeout(() => lista.reload(), 3000); }}>
            <FileText className="size-4" /> Gerar e salvar agora</Button>
        </div>
      </PageHeader>
      <ErrorBox error={lista.error ?? (preview.error?.includes("Nenhuma") ? null : preview.error)} />
      {msg && <div className="mb-4 rounded-md border bg-muted/40 p-3 text-sm">{msg}</div>}

      <div className="grid gap-6 lg:grid-cols-[200px_minmax(0,1fr)]">
        <Card>
          <CardHeader><CardTitle>Salvos</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            <button className={`block w-full rounded px-2 py-1 text-left hover:bg-accent ${!sel ? "bg-accent font-medium" : ""}`} onClick={() => setSel(null)}>Situação atual</button>
            {lista.data?.map((r) => (
              <button key={r.id} className={`block w-full rounded px-2 py-1 text-left hover:bg-accent ${sel === r.id ? "bg-accent font-medium" : ""}`} onClick={() => setSel(r.id)}>
                {r.referencia}<div className="text-xs text-muted-foreground">{fmtDate(r.criado_em)}</div>
              </button>
            ))}
          </CardContent>
        </Card>

        {!d ? <p className="text-sm text-muted-foreground">Nenhuma edição processada ainda.</p> : (
          <div className="grid min-w-0 grid-cols-1 gap-6">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {[["Edição", `RPI ${d.edicao}`], ["Publicação", fmtDay(d.data_publicacao)],
                ["Ausência de procurador confirmada", fmtNum(d.procurador_confirmado_inpi)], ["Custo de IA na semana", `US$ ${d.custo_ia_semana_usd}`]].map(([k, v]) => (
                <Card key={k}><CardHeader><CardDescription>{k}</CardDescription><CardTitle className="text-2xl">{v}</CardTitle></CardHeader></Card>
              ))}
            </div>
            <div className="grid gap-6 xl:grid-cols-2">
              <Card>
                <CardHeader><CardTitle>Oportunidades por categoria</CardTitle><CardDescription>Na edição {d.edicao}</CardDescription></CardHeader>
                <CardContent><Table>
                  <TableHeader><TableRow><TableHead>Categoria</TableHead><TableHead className="text-right">Elegíveis</TableHead><TableHead className="text-right">Descartadas</TableHead></TableRow></TableHeader>
                  <TableBody>{d.oportunidades_por_categoria.map((o: any) => (
                    <TableRow key={o.categoria}><TableCell>{categoriaLabel[o.categoria] ?? o.categoria}</TableCell>
                      <TableCell className="text-right tabular-nums">{fmtNum(o.elegiveis)}</TableCell><TableCell className="text-right tabular-nums">{fmtNum(o.descartadas)}</TableCell></TableRow>
                  ))}</TableBody>
                </Table></CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>Leads por prioridade</CardTitle><CardDescription>Todos os leads ativos · {fmtNum(d.revisoes_abertas)} revisão(ões) aberta(s)</CardDescription></CardHeader>
                <CardContent className="grid grid-cols-3 gap-3">
                  {d.leads_por_prioridade.map((p: any) => (
                    <Link key={p.prioridade ?? "?"} href={`/leads?prioridade=${p.prioridade ?? ""}`} className="rounded-lg border p-4 hover:border-ring">
                      <div className="text-sm text-muted-foreground">{p.prioridade ?? "sem prioridade"}</div><div className="text-2xl font-semibold tabular-nums">{fmtNum(p.n)}</div>
                    </Link>
                  ))}
                </CardContent>
              </Card>
            </div>
            <Card>
              <CardHeader><CardTitle>Principais leads da edição</CardTitle></CardHeader>
              <CardContent><Table>
                <TableHeader><TableRow><TableHead>Prioridade</TableHead><TableHead>Titular</TableHead><TableHead>Categoria</TableHead><TableHead>Prazo estimado</TableHead><TableHead>Contatos validados</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
                <TableBody>{d.top_leads.map((l: any) => (
                  <TableRow key={l.id}>
                    <TableCell><Badge variant={prioridadeVariant[l.prioridade] ?? "outline"}>{l.prioridade}</Badge> <span className="text-xs text-muted-foreground">{l.score}</span></TableCell>
                    <TableCell><Link href={`/leads/${l.id}`} className="underline-offset-4 hover:underline">{l.titular}</Link><span className="ml-1 text-xs text-muted-foreground">{l.uf}</span></TableCell>
                    <TableCell>{categoriaLabel[l.categoria_principal] ?? "—"}</TableCell><TableCell>{fmtDay(l.prazo_ate)}</TableCell>
                    <TableCell className="tabular-nums">{l.contatos_validados}</TableCell><TableCell>{leadStatusLabel[l.status] ?? l.status}</TableCell>
                  </TableRow>
                ))}</TableBody>
              </Table></CardContent>
            </Card>
          </div>
        )}
      </div>
    </>
  );
}
