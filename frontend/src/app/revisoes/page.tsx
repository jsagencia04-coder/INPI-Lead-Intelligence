"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { useApi } from "@/components/use-api";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
const ENTIDADE: Record<string, string> = { holder: "Titular", process: "Processo", despacho_type: "Despacho", sistema: "Sistema", lead: "Lead" };

function link(r: any) {
  if (r.entidade === "holder" && r.lead_id) return `/leads/${r.lead_id}`;
  if (r.entidade === "process") return `/processos?q=${r.entidade_id}`;
  if (r.entidade === "despacho_type") return "/despachos";
  if (r.entidade === "sistema") return "/operacao";
  return null;
}

export default function RevisoesPage() {
  const { data, error, reload } = useApi<any[]>("/api/reviews");
  const [texto, setTexto] = useState<Record<number, string>>({});
  return (
    <>
      <PageHeader title="Revisões humanas" description="Tudo que o sistema não decide sozinho: homônimos, divergências com o INPI, despachos novos, bloqueios." />
      <ErrorBox error={error} />
      <Card><CardContent><Table>
        <TableHeader><TableRow><TableHead>Quando</TableHead><TableHead>Sobre</TableHead><TableHead>Motivo</TableHead><TableHead>Resolução</TableHead></TableRow></TableHeader>
        <TableBody>
          {data?.length === 0 && <TableRow><TableCell colSpan={4} className="text-muted-foreground">Nenhuma revisão aberta.</TableCell></TableRow>}
          {data?.map((r) => {
            const href = link(r);
            return (
              <TableRow key={r.id} className="align-top">
                <TableCell className="text-xs">{fmtDate(r.criado_em)}</TableCell>
                <TableCell>{href ? <Link href={href} className="underline-offset-4 hover:underline">{ENTIDADE[r.entidade] ?? r.entidade} {r.entidade_id}</Link> : `${r.entidade} ${r.entidade_id}`}</TableCell>
                <TableCell className="max-w-xl whitespace-normal text-sm">{r.motivo}</TableCell>
                <TableCell>
                  <div className="flex gap-2">
                    <Input placeholder="O que foi decidido" value={texto[r.id] ?? ""} onChange={(e) => setTexto({ ...texto, [r.id]: e.target.value })} className="w-56" />
                    <Button size="sm" variant="outline" disabled={!texto[r.id]}
                      onClick={async () => { await api(`/api/reviews/${r.id}/resolve`, { method: "POST", body: JSON.stringify({ texto: texto[r.id] }) }); reload(); }}>Resolver</Button>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table></CardContent></Card>
    </>
  );
}
