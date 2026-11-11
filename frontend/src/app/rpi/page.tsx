"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { Download, RefreshCw, Upload } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { useApi } from "@/components/use-api";
import { api, apiDownload, apiUpload } from "@/lib/api";
import { categoriaLabel, editionStatusLabel, fmtBytes, fmtDate, fmtNum } from "@/lib/format";
import type { RpiEdition } from "@/lib/types";

const statusVariant: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  parsed: "secondary",
  error: "destructive",
  detected: "outline",
};

export default function RpiPage() {
  const { data, error, reload } = useApi<RpiEdition[]>("/api/rpi/editions", 5000);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      setMsg(ok);
      await reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    await run(() => apiUpload("/api/rpi/upload", f), `Arquivo ${f.name} recebido. A interpretação foi enfileirada.`);
    e.target.value = "";
  }

  return (
    <>
      <PageHeader
        title="Edições da RPI"
        description="Seção de marcas. O XML oficial é guardado sem alterações, com hash SHA-256."
      >
        <div className="flex gap-2">
          <input ref={fileRef} type="file" accept=".zip" className="hidden" onChange={onUpload} />
          <Button variant="outline" disabled={busy} onClick={() => fileRef.current?.click()}>
            <Upload className="size-4" /> Enviar RM.zip
          </Button>
          <Button disabled={busy} onClick={() => run(() => api("/api/rpi/discover", { method: "POST" }), "Verificação enfileirada.")}>
            <RefreshCw className="size-4" /> Verificar novas edições
          </Button>
        </div>
      </PageHeader>
      <ErrorBox error={error} />
      {msg && <div className="mb-4 rounded-md border bg-muted/40 p-3 text-sm">{msg}</div>}

      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Edição</TableHead><TableHead>Publicação</TableHead><TableHead>Status</TableHead>
                <TableHead className="text-right">No XML</TableHead><TableHead className="text-right">Importados</TableHead>
                <TableHead className="text-right">Elegíveis</TableHead><TableHead>Por categoria</TableHead>
                <TableHead>Descartes</TableHead><TableHead>Original</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.length === 0 && (
                <TableRow>
                  <TableCell colSpan={10} className="text-muted-foreground">
                    Nenhuma edição ainda. Clique em &quot;Verificar novas edições&quot; (o worker precisa estar rodando).
                  </TableCell>
                </TableRow>
              )}
              {data?.map((e) => {
                const s = e.stats ?? {};
                return (
                  <TableRow key={e.numero} className="align-top">
                    <TableCell className="font-medium">
                      <Link className="underline-offset-4 hover:underline" href={`/processos?edicao=${e.numero}&oportunidade=elegivel`}>
                        {e.numero}
                      </Link>
                    </TableCell>
                    <TableCell>{e.data_publicacao ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant={statusVariant[e.status] ?? "default"}>{editionStatusLabel[e.status] ?? e.status}</Badge>
                      {e.observacoes && <div className="mt-1 max-w-56 whitespace-normal text-xs text-destructive">{e.observacoes}</div>}
                      {!!s.despachos_novos?.length && (
                        <div className="mt-1 text-xs">
                          <Link href="/despachos" className="text-amber-700 underline">
                            {s.despachos_novos.length} despacho(s) novo(s) para classificar
                          </Link>
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{fmtNum(s.processos_no_xml)}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtNum(s.processos_importados)}</TableCell>
                    <TableCell className="text-right tabular-nums font-medium">{fmtNum(s.oportunidades_elegiveis)}</TableCell>
                    <TableCell className="text-xs whitespace-normal">
                      {Object.entries(s.elegiveis_por_categoria ?? {}).map(([k, v]) => (
                        <div key={k}>{categoriaLabel[k] ?? k}: {fmtNum(v)}</div>
                      ))}
                    </TableCell>
                    <TableCell className="text-xs whitespace-normal">
                      {Object.entries(s.motivos_descarte ?? {}).map(([k, v]) => (
                        <div key={k}>{k}: {fmtNum(v)}</div>
                      ))}
                    </TableCell>
                    <TableCell className="text-xs">
                      {e.arquivos.map((f) => (
                        <button
                          key={f.id}
                          className="flex items-center gap-1 underline-offset-4 hover:underline"
                          title={`SHA-256 ${f.sha256}\nFonte: ${f.source_url}\nBaixado em ${fmtDate(f.baixado_em)}`}
                          onClick={() => apiDownload(`/api/rpi/files/${f.id}`, f.nome_arquivo)}
                        >
                          <Download className="size-3" /> {f.nome_arquivo} ({fmtBytes(f.bytes)})
                        </button>
                      ))}
                    </TableCell>
                    <TableCell>
                      {e.arquivos.some((f) => f.formato === "zip") ? (
                        <Button size="sm" variant="outline" disabled={busy}
                          onClick={() => run(() => api(`/api/rpi/editions/${e.numero}/parse`, { method: "POST" }), `Reprocessamento da ${e.numero} enfileirado.`)}>
                          Reprocessar
                        </Button>
                      ) : (
                        <Button size="sm" variant="outline" disabled={busy}
                          onClick={() => run(() => api(`/api/rpi/editions/${e.numero}/collect`, { method: "POST" }), `Coleta da ${e.numero} enfileirada.`)}>
                          Coletar
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </>
  );
}
