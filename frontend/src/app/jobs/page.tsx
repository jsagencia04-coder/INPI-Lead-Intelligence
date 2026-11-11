"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { JobStatusBadge } from "@/components/status-badge";
import { useApi } from "@/components/use-api";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Job } from "@/lib/types";

function JobsInner() {
  const sp = useSearchParams();
  const status = sp.get("status");
  const tipo = sp.get("tipo");
  const qs = new URLSearchParams({ ...(status ? { status } : {}), ...(tipo ? { tipo } : {}) }).toString();
  const { data, error, reload } = useApi<Job[]>(`/api/jobs${qs ? `?${qs}` : ""}`, 5000);
  const [busy, setBusy] = useState(false);

  async function ping() {
    setBusy(true);
    try {
      await api("/api/jobs", { method: "POST", body: JSON.stringify({ tipo: "system.ping" }) });
      await reload();
    } finally {
      setBusy(false);
    }
  }

  async function retry(id: number) {
    await api(`/api/jobs/${id}/retry`, { method: "POST" });
    await reload();
  }

  return (
    <>
      <PageHeader title="Agentes e jobs" description={status || tipo ? `Filtro: ${[status, tipo].filter(Boolean).join(" · ")}` : "Fila de execução de todos os agentes"}>
        <Button onClick={ping} disabled={busy} variant="outline">Testar pipeline (ping)</Button>
      </PageHeader>
      <ErrorBox error={error} />
      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead><TableHead>Agente</TableHead><TableHead>Status</TableHead>
                <TableHead>Tentativas</TableHead><TableHead>Worker</TableHead><TableHead>Criado</TableHead>
                <TableHead>Finalizado</TableHead><TableHead>Erro</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.length === 0 && (
                <TableRow><TableCell colSpan={9} className="text-muted-foreground">Nenhum job.</TableCell></TableRow>
              )}
              {data?.map((j) => (
                <TableRow key={j.id}>
                  <TableCell>{j.id}</TableCell>
                  <TableCell className="font-mono text-xs">{j.tipo}</TableCell>
                  <TableCell><JobStatusBadge status={j.status} /></TableCell>
                  <TableCell>{j.tentativas}</TableCell>
                  <TableCell className="text-xs">{j.locked_by ?? "—"}</TableCell>
                  <TableCell>{fmtDate(j.criado_em)}</TableCell>
                  <TableCell>{fmtDate(j.finalizado_em)}</TableCell>
                  <TableCell className="max-w-64 truncate text-xs text-destructive" title={j.ultimo_erro ?? ""}>
                    {j.ultimo_erro?.split("\n")[0] ?? ""}
                  </TableCell>
                  <TableCell>
                    {(j.status === "dead" || j.status === "failed") && (
                      <Button size="sm" variant="outline" onClick={() => retry(j.id)}>Reprocessar</Button>
                    )}
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

export default function JobsPage() {
  return <Suspense><JobsInner /></Suspense>;
}
