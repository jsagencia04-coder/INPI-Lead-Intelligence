"use client";

import { useState } from "react";
import { CheckCircle2, Circle, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { Select } from "@/components/select";
import { useApi } from "@/components/use-api";
import { api } from "@/lib/api";
import { WA_STATUS, fmtHora, type WaMensagem, type WaStatus } from "@/lib/wa-api";
import { formatWhats } from "@/lib/whatsapp";
import type { Paged } from "@/lib/types";

const PAGE = 50;

export default function WhatsappPage() {
  const { data: st, error } = useApi<WaStatus>("/api/whatsapp/status", 15000);
  const [filtro, setFiltro] = useState("");
  const [offset, setOffset] = useState(0);
  const p = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (filtro === "entrada" || filtro === "saida") p.set("direcao", filtro);
  else if (filtro) p.set("status", filtro);
  const { data: msgs, reload } = useApi<Paged<WaMensagem>>(`/api/whatsapp/messages?${p}`, 15000);
  const [tpl, setTpl] = useState<{ ok: boolean; status: string | null; motivo: string | null } | null>(null);
  const [verificando, setVerificando] = useState(false);

  const verificar = async () => {
    setVerificando(true);
    try { setTpl(await api("/api/whatsapp/template/verificar", { method: "POST" })); }
    catch (e) { setTpl({ ok: false, status: null, motivo: e instanceof Error ? e.message : String(e) }); }
    finally { setVerificando(false); }
  };
  const cancelar = async (id: number) => {
    await api(`/api/whatsapp/messages/${id}/cancel`, { method: "POST" }).catch(() => null);
    reload();
  };

  return (
    <>
      <PageHeader title="WhatsApp Business (API oficial)" description="Integração com a Cloud API da Meta. As credenciais ficam só no servidor e nunca aparecem aqui." />
      <ErrorBox error={error} />
      {st && (
        <div className={`mb-4 rounded-md border p-3 text-sm ${st.modo === "real" ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
          {st.modo === "real"
            ? <>Modo <b>real</b>: mensagens aprovadas saem pela API oficial, só para os {st.numeros_teste} número(s) de homologação.</>
            : <>Modo <b>simulação</b>: nenhuma mensagem sai do sistema. O que seria enviado fica registrado abaixo como “simulada”.</>}
        </div>
      )}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader><CardTitle className="text-base">Configuração</CardTitle></CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            {st && Object.entries(st.credenciais).map(([k, ok]) => (
              <div key={k} className="flex items-center gap-2">
                {ok ? <CheckCircle2 className="size-4 text-emerald-600" /> : <Circle className="size-4 text-muted-foreground" />}
                <code className="text-xs">{k}</code>
                <span className="text-xs text-muted-foreground">{ok ? "definida" : "falta"}</span>
              </div>
            ))}
            <div className="flex items-center gap-2">
              {st?.envio_ativo ? <CheckCircle2 className="size-4 text-emerald-600" /> : <Circle className="size-4 text-muted-foreground" />}
              <code className="text-xs">WHATSAPP_ENVIO_ATIVO</code>
              <span className="text-xs text-muted-foreground">{st?.envio_ativo ? "ligado" : "desligado"}</span>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Template e webhook</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div>Template: <b>{st?.template.nome ?? "não definido"}</b> ({st?.template.idioma})</div>
            <Button size="sm" variant="outline" onClick={verificar} disabled={verificando || !st?.configurado}>
              <RefreshCw className={`size-4 ${verificando ? "animate-spin" : ""}`} /> Consultar aprovação na Meta
            </Button>
            {tpl && <div className={tpl.ok ? "text-emerald-700" : "text-amber-800"}>{tpl.ok ? "Aprovado pela Meta." : `${tpl.status ?? "Não confirmado"}: ${tpl.motivo ?? ""}`}</div>}
            <div className="pt-1 text-xs text-muted-foreground">Endereço do webhook para cadastrar na Meta:<br /><code>https://SEU-DOMINIO{st?.webhook}</code></div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Hoje</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div>Aceitas pela Meta: <b>{st?.enviadas_hoje ?? "—"}</b> de {st?.limites.por_dia} (limite diário)</div>
            <div>Na fila: <b>{st?.na_fila ?? "—"}</b></div>
            <div>Respostas recebidas: <b>{st?.recebidas_hoje ?? "—"}</b></div>
            <div className="text-xs text-muted-foreground">Ritmo máximo: {st?.limites.por_minuto} por minuto.</div>
            {st && st.pendencias_para_envio_real.length > 0 && (
              <div className="pt-2 text-xs text-amber-800">Falta para o envio real: {st.pendencias_para_envio_real.join("; ")}.</div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-lg font-semibold">Histórico de mensagens</h2>
        <Select value={filtro} onChange={(v) => { setFiltro(v); setOffset(0); }} placeholder="Todas"
          options={{ saida: "Enviadas por nós", entrada: "Respostas recebidas", ...Object.fromEntries(Object.entries(WA_STATUS).map(([k, v]) => [k, v.rotulo])) }} />
      </div>
      <Card>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Quando</TableHead><TableHead>Sentido</TableHead><TableHead>Titular / número</TableHead><TableHead>Processo</TableHead>
                <TableHead>Conteúdo</TableHead><TableHead>Status</TableHead><TableHead>Linha do tempo</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {msgs?.items.length === 0 && <TableRow><TableCell colSpan={8} className="text-muted-foreground">Nenhuma mensagem.</TableCell></TableRow>}
              {msgs?.items.map((m) => (
                <TableRow key={m.id} className="align-top">
                  <TableCell className="whitespace-nowrap text-xs">{fmtHora(m.criado_em)}</TableCell>
                  <TableCell className="text-xs">{m.direcao === "saida" ? "→ saída" : "← entrada"}{m.modo === "simulacao" && <Badge variant="outline" className="ml-1">simulação</Badge>}</TableCell>
                  <TableCell className="max-w-56 text-xs"><div className="truncate text-sm">{m.titular ?? "Número não identificado"}</div>{formatWhats(m.numero)}</TableCell>
                  <TableCell className="text-xs">{m.numero_processo ?? "—"}</TableCell>
                  <TableCell className="max-w-72 text-xs">{m.template_nome && <div className="text-muted-foreground">template {m.template_nome}</div>}<div className="line-clamp-3">{m.corpo ?? "—"}</div></TableCell>
                  <TableCell className="text-xs"><span className={WA_STATUS[m.status]?.cor}>{WA_STATUS[m.status]?.rotulo ?? m.status}</span>{m.motivo && <div className="max-w-56 text-muted-foreground">{m.motivo}</div>}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {m.aceita_em && <div>aceita {fmtHora(m.aceita_em)}</div>}
                    {m.enviada_em && <div>enviada {fmtHora(m.enviada_em)}</div>}
                    {m.entregue_em && <div>entregue {fmtHora(m.entregue_em)}</div>}
                    {m.lida_em && <div>lida {fmtHora(m.lida_em)}</div>}
                    {m.falhou_em && <div>falhou {fmtHora(m.falhou_em)}</div>}
                  </TableCell>
                  <TableCell>{m.status === "na_fila" && <Button size="sm" variant="outline" onClick={() => cancelar(m.id)}>Cancelar</Button>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {msgs && msgs.total > PAGE && (
            <div className="mt-4 flex items-center justify-end gap-2 text-sm">
              <span className="text-muted-foreground">{offset + 1}–{Math.min(offset + PAGE, msgs.total)} de {msgs.total}</span>
              <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>Anterior</Button>
              <Button size="sm" variant="outline" disabled={offset + PAGE >= msgs.total} onClick={() => setOffset(offset + PAGE)}>Próxima</Button>
            </div>
          )}
        </CardContent>
      </Card>
      <p className="mt-3 text-xs text-muted-foreground">
        “Aceita” vem da resposta da Meta; “enviada”, “entregue” e “lida” só aparecem quando a Meta avisa pelo webhook. O sistema não presume entrega.
      </p>
    </>
  );
}
