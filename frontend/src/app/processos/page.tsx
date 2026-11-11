"use client";

import { Suspense, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { useApi } from "@/components/use-api";
import { categoriaLabel, procuradorCurto, procuradorLabel } from "@/lib/format";
import type { Paged, ProcessRow } from "@/lib/types";

const PAGE = 50;

function Select({ value, onChange, options, placeholder }: {
  value: string; onChange: (v: string) => void; options: Record<string, string>; placeholder: string;
}) {
  return (
    <select className="h-9 rounded-md border bg-background px-2 text-sm" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder}</option>
      {Object.entries(options).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
    </select>
  );
}

function ProcessosInner() {
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

  const params = new URLSearchParams();
  for (const k of ["oportunidade", "categoria", "edicao", "procurador_status"]) {
    const v = sp.get(k);
    if (v) params.set(k, v);
  }
  if (q.trim()) params.set("q", q.trim());
  params.set("limit", String(PAGE));
  params.set("offset", String(offset));
  const { data, error } = useApi<Paged<ProcessRow>>(`/api/processes?${params}`);

  return (
    <>
      <PageHeader
        title="Processos"
        description={data ? `${data.total.toLocaleString("pt-BR")} processo(s)${sp.get("edicao") ? ` · RPI ${sp.get("edicao")}` : ""}` : undefined}
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input placeholder="Nº do processo, marca ou titular" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} className="w-72" />
        <Select value={sp.get("oportunidade") ?? ""} onChange={(v) => setParam("oportunidade", v)} placeholder="Todas as situações"
          options={{ elegivel: "Elegíveis (sem procurador)", descartada: "Descartados" }} />
        <Select value={sp.get("categoria") ?? ""} onChange={(v) => setParam("categoria", v)} placeholder="Todas as categorias"
          options={categoriaLabel} />
        {sp.get("edicao") && <Button variant="ghost" onClick={() => setParam("edicao", "")}>Limpar edição</Button>}
      </div>
      <ErrorBox error={error} />
      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Processo</TableHead><TableHead>Marca</TableHead><TableHead>Titular</TableHead>
                <TableHead>Despacho</TableHead><TableHead>Classes</TableHead><TableHead>Procurador</TableHead>
                <TableHead>Situação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.items.length === 0 && (
                <TableRow><TableCell colSpan={7} className="text-muted-foreground">Nenhum processo encontrado.</TableCell></TableRow>
              )}
              {data?.items.map((p) => (
                <TableRow key={p.numero_processo}>
                  <TableCell className="font-mono">{p.numero_processo}</TableCell>
                  <TableCell>{p.marca_nome ?? <span className="text-muted-foreground">não informada</span>}</TableCell>
                  <TableCell className="max-w-56 truncate" title={p.titulares ?? ""}>{p.titulares ?? "—"}</TableCell>
                  <TableCell>
                    {p.categoria ? <span>{categoriaLabel[p.categoria]}</span> : "—"}
                    {p.despacho_codigo && <span className="ml-1 font-mono text-xs text-muted-foreground">{p.despacho_codigo} · RPI {p.rpi}</span>}
                  </TableCell>
                  <TableCell>{p.classes_nice.join(", ") || "—"}</TableCell>
                  <TableCell className="text-xs" title={`${procuradorLabel[p.procurador_status]}${p.procurador_fonte ? ` · fonte ${p.procurador_fonte}` : ""}`}>
                    {p.procurador_nome ?? procuradorCurto[p.procurador_status]}
                  </TableCell>
                  <TableCell>
                    {p.oportunidade_status === "elegivel" && <Badge>Elegível</Badge>}
                    {p.oportunidade_status === "descartada" && <Badge variant="outline" title={p.motivo_descarte ?? ""}>Descartado: {p.motivo_descarte}</Badge>}
                  </TableCell>
                </TableRow>
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
    </>
  );
}

export default function ProcessosPage() {
  return <Suspense><ProcessosInner /></Suspense>;
}
