"use client";

import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { JobStatusBadge } from "@/components/status-badge";
import { useApi } from "@/components/use-api";
import { fmtDate } from "@/lib/format";
import type { DashboardSummary, Edition, Job } from "@/lib/types";

const kpis: { key: keyof DashboardSummary; label: string; href?: string }[] = [
  { key: "processos_importados", label: "Processos importados", href: "/processos" },
  { key: "processos_sem_procurador", label: "Processos sem procurador", href: "/processos?oportunidade=elegivel" },
  { key: "processos_descartados", label: "Processos descartados", href: "/processos?oportunidade=descartada" },
  { key: "leads_encontrados", label: "Leads encontrados", href: "/leads" },
  { key: "leads_whatsapp_validado", label: "Leads com WhatsApp validado", href: "/leads?whatsapp=validado" },
  { key: "contatos_validados", label: "Contatos validados", href: "/leads" },
  { key: "leads_sem_contato", label: "Leads sem contato", href: "/leads?status=sem_contato" },
  { key: "pesquisas_pendentes", label: "Pesquisas pendentes", href: "/jobs?status=queued" },
  { key: "agentes_em_execucao", label: "Agentes em execução", href: "/jobs?status=running" },
  { key: "revisoes_abertas", label: "Revisões humanas abertas", href: "/revisoes" },
  { key: "procurador_ausente_confirmado", label: "Ausência de procurador confirmada no INPI", href: "/processos?procurador_status=sem_confirmado" },
  { key: "custo_ia_semana_usd", label: "Custo de IA na semana (US$)", href: "/operacao" },
];

export default function Dashboard() {
  const summary = useApi<DashboardSummary>("/api/dashboard/summary", 10000);
  const history = useApi<{ edicoes: Edition[]; jobs: Job[] }>("/api/dashboard/history?limit=10", 10000);

  return (
    <>
      <PageHeader title="Dashboard" description="Atualiza a cada 10 segundos." />
      <ErrorBox error={summary.error} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {kpis.map(({ key, label, href }) => {
          const value = summary.data ? Number(summary.data[key]).toLocaleString("pt-BR") : "…";
          const card = (
            <Card className={href ? "hover:border-ring transition-colors" : ""}>
              <CardHeader>
                <CardDescription>{label}</CardDescription>
                <CardTitle className="text-3xl tabular-nums">{value}</CardTitle>
              </CardHeader>
            </Card>
          );
          return href ? <Link key={key} href={href}>{card}</Link> : <div key={key}>{card}</div>;
        })}
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Edições da RPI</CardTitle>
            <CardDescription><Link href="/rpi" className="underline">Ver todas as edições</Link></CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow><TableHead>Edição</TableHead><TableHead>Publicação</TableHead><TableHead>Status</TableHead><TableHead>Processada</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {history.data?.edicoes.length === 0 && (
                  <TableRow><TableCell colSpan={4} className="text-muted-foreground">Nenhuma edição importada ainda.</TableCell></TableRow>
                )}
                {history.data?.edicoes.map((e) => (
                  <TableRow key={e.numero}>
                    <TableCell className="font-medium">{e.numero}</TableCell>
                    <TableCell>{e.data_publicacao ?? "—"}</TableCell>
                    <TableCell>{e.status}</TableCell>
                    <TableCell>{fmtDate(e.processada_em)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Atividade dos agentes</CardTitle>
            <CardDescription><Link href="/jobs" className="underline">Ver todos os jobs</Link></CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow><TableHead>#</TableHead><TableHead>Agente</TableHead><TableHead>Status</TableHead><TableHead>Criado</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {history.data?.jobs.length === 0 && (
                  <TableRow><TableCell colSpan={4} className="text-muted-foreground">Nenhum job ainda.</TableCell></TableRow>
                )}
                {history.data?.jobs.map((j) => (
                  <TableRow key={j.id}>
                    <TableCell>{j.id}</TableCell>
                    <TableCell className="font-mono text-xs">{j.tipo}</TableCell>
                    <TableCell><JobStatusBadge status={j.status} /></TableCell>
                    <TableCell>{fmtDate(j.criado_em)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
