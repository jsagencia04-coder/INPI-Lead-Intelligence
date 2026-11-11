"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { useApi } from "@/components/use-api";
import { api } from "@/lib/api";
import { categoriaLabel, fmtDate, fmtNum } from "@/lib/format";
import type { DespachoType } from "@/lib/types";

export default function DespachosPage() {
  const { data, error, reload } = useApi<DespachoType[]>("/api/rpi/despachos");

  async function save(codigo: string, patch: Partial<Pick<DespachoType, "categoria_comercial" | "ativo_para_leads">>) {
    await api(`/api/rpi/despachos/${codigo}`, { method: "PATCH", body: JSON.stringify(patch) });
    await reload();
  }

  return (
    <>
      <PageHeader
        title="Catálogo de despachos"
        description="Define quais despachos geram oportunidades. Mudanças valem para as próximas importações e para reprocessamentos."
      />
      <ErrorBox error={error} />
      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Código</TableHead><TableHead>Nome (como publicado na RPI)</TableHead>
                <TableHead>Categoria</TableHead><TableHead>Gera leads</TableHead>
                <TableHead className="text-right">Publicações</TableHead><TableHead>Origem</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.map((d) => (
                <TableRow key={d.codigo} className={d.revisar ? "bg-amber-50" : ""}>
                  <TableCell className="font-mono text-xs">
                    {d.codigo} {d.revisar && <Badge variant="outline" className="ml-1 border-amber-500 text-amber-700">novo</Badge>}
                  </TableCell>
                  <TableCell className="max-w-md whitespace-normal">{d.nome}</TableCell>
                  <TableCell>
                    <select
                      className="h-8 rounded-md border bg-background px-2 text-sm"
                      value={d.categoria_comercial}
                      onChange={(e) => save(d.codigo, { categoria_comercial: e.target.value })}
                    >
                      {Object.entries(categoriaLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </TableCell>
                  <TableCell>
                    <input
                      type="checkbox"
                      className="size-4 accent-primary"
                      checked={d.ativo_para_leads}
                      onChange={(e) => save(d.codigo, { ativo_para_leads: e.target.checked })}
                    />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{fmtNum(d.publicacoes)}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {d.confirmado_por ? `${d.confirmado_por} em ${fmtDate(d.confirmado_em)}` : d.fonte}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </>
  );
}
