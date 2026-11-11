"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { JobStatusBadge } from "@/components/status-badge";
import { useApi } from "@/components/use-api";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
const DESCR: Record<string, string> = {
  "rpi-descoberta": "Agente 01: procura novas edições da RPI",
  "inpi-verificacao": "Agente 03: consulta processos elegíveis no INPI",
  "cnpj-receita": "Cruza titulares com a base CNPJ da Receita (baixa ~8 GB por mês)",
  "pesquisa-gratuita": "Agente 04 (grátis): lê os sites oficiais dos titulares e extrai contatos publicados",
  "pesquisa-web": "Agente 04 (pago): pesquisa contatos com Claude (exige ANTHROPIC_API_KEY)",
  "leads-montagem": "Agente 05: monta, deduplica e pontua os leads",
  "resumos-comerciais": "Agente 06: resumo e sugestão de abordagem",
  "relatorio-semanal": "Salva o relatório da última edição",
};

export default function OperacaoPage() {
  const { data, error, reload } = useApi<any>("/api/metrics", 10000);
  async function toggle(nome: string, ativo: boolean) {
    await api(`/api/schedules/${nome}`, { method: "PATCH", body: JSON.stringify({ ativo }) });
    reload();
  }
  return (
    <>
      <PageHeader title="Operação" description="Agendamentos dos agentes, saúde da fila e custo de IA. Atualiza a cada 10 s." />
      <ErrorBox error={error} />
      {data && !data.ia_configurada && (
        <div className="mb-4 rounded-md border bg-muted/40 p-3 text-sm">
          <b>Modo gratuito:</b> os contatos vêm da leitura dos sites oficiais (<i>pesquisa-gratuita</i>), da base CNPJ da
          Receita (<i>cnpj-receita</i>, ligue abaixo, ~8 GB) e da busca assistida na tela do lead. A pesquisa com IA
          (<i>pesquisa-web</i>, paga) fica parada até haver <code>ANTHROPIC_API_KEY</code> no <code>backend/.env</code>.
        </div>
      )}
      {data && (
        <div className="grid grid-cols-1 gap-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <Card><CardHeader><CardDescription>Falhas definitivas (24 h)</CardDescription><CardTitle className="text-3xl">{data.falhas_24h}</CardTitle></CardHeader></Card>
            <Card><CardHeader><CardDescription>Custo de IA na semana</CardDescription>
              <CardTitle className="text-3xl">US$ {data.custo_ia.reduce((s: number, c: any) => s + Number(c.usd), 0).toFixed(2)}</CardTitle></CardHeader></Card>
            <Card><CardHeader><CardDescription>Buscas web na semana</CardDescription>
              <CardTitle className="text-3xl">{data.custo_ia.reduce((s: number, c: any) => s + Number(c.buscas ?? 0), 0)}</CardTitle></CardHeader></Card>
          </div>
          <Card>
            <CardHeader><CardTitle>Agendamentos</CardTitle><CardDescription>Ligue ou desligue cada agente automático.</CardDescription></CardHeader>
            <CardContent><Table>
              <TableHeader><TableRow><TableHead>Ativo</TableHead><TableHead>Agendamento</TableHead><TableHead>A cada</TableHead><TableHead>Próxima execução</TableHead></TableRow></TableHeader>
              <TableBody>{data.agendamentos.map((s: any) => (
                <TableRow key={s.nome}>
                  <TableCell><input type="checkbox" className="size-4 accent-primary" checked={s.ativo} onChange={(e) => toggle(s.nome, e.target.checked)} /></TableCell>
                  <TableCell><div className="font-medium">{s.nome}</div><div className="text-xs text-muted-foreground">{DESCR[s.nome] ?? s.tipo}</div></TableCell>
                  <TableCell>{s.intervalo_minutos >= 1440 ? `${s.intervalo_minutos / 1440} dia(s)` : `${s.intervalo_minutos} min`}</TableCell>
                  <TableCell>{s.ativo ? fmtDate(s.proximo_em) : "—"}</TableCell>
                </TableRow>
              ))}</TableBody>
            </Table></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Último resultado por agente</CardTitle></CardHeader>
            <CardContent><Table>
              <TableHeader><TableRow><TableHead>Agente</TableHead><TableHead>Status</TableHead><TableHead>Quando</TableHead><TableHead>Erro</TableHead></TableRow></TableHeader>
              <TableBody>{data.ultimo_por_agente.map((j: any) => (
                <TableRow key={j.tipo}><TableCell className="font-mono text-xs">{j.tipo}</TableCell><TableCell><JobStatusBadge status={j.status} /></TableCell>
                  <TableCell>{fmtDate(j.finalizado_em)}</TableCell><TableCell className="max-w-md truncate text-xs text-destructive">{j.erro?.split("\n")[0]}</TableCell></TableRow>
              ))}</TableBody>
            </Table></CardContent>
          </Card>
        </div>
      )}
    </>
  );
}
