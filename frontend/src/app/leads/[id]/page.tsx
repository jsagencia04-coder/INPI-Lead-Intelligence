"use client";

import { use, useState } from "react";
import { Check, ExternalLink, RefreshCw, Search, Sparkles, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { CLASSE, MEDIDA, PRAZO, SERVICO, TIPO_DECISAO, textoPrazo, type Oportunidade } from "@/lib/servicos";
import { cn } from "@/lib/utils";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { Select } from "@/components/select";
import { useApi } from "@/components/use-api";
import { BuscaAssistida } from "@/components/busca-assistida";
import { WhatsappCard } from "@/components/whatsapp-card";
import { api } from "@/lib/api";
import {
  categoriaLabel, diasAte, fmtDate, fmtDay, leadStatusLabel, prioridadeVariant, procuradorLabel, verificacaoLabel,
} from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Lead = Record<string, any>;

const SITUACAO_CNPJ: Record<string, string> = { "01": "Nula", "02": "Ativa", "03": "Suspensa", "04": "Inapta", "08": "Baixada" };
const TIPOS_CONTATO = { site: "Site", email: "E-mail", telefone: "Telefone", whatsapp: "WhatsApp", instagram: "Instagram",
  linkedin: "LinkedIn", facebook: "Facebook", tiktok: "TikTok", youtube: "YouTube" };
const SCORE_LABEL: Record<string, string> = { categoria: "Categoria do despacho", urgencia: "Urgência do prazo",
  processos: "Mais de um processo", contatos: "Contatos", pessoa_juridica: "Pessoa jurídica",
  procurador_confirmado: "Ausência de procurador confirmada", cnpj_ambiguo: "CNPJ ambíguo" };

function Section({ title, description, actions, children }: {
  title: string; description?: string; actions?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="grid gap-1.5">
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        {actions}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

const Empty = ({ children }: { children: React.ReactNode }) => <p className="text-sm text-muted-foreground">{children}</p>;

export default function LeadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: lead, error, reload } = useApi<Lead>(`/api/leads/${id}`);
  const { data: ops } = useApi<{ ia_configurada: boolean }>("/api/metrics");
  const [msg, setMsg] = useState<string | null>(null);
  const [motivo, setMotivo] = useState("");
  const [nota, setNota] = useState("");
  const [novo, setNovo] = useState({ tipo: "email", valor: "", fonte_url: "" });
  const [prosp, setProsp] = useState({ canal: "email", contact_id: "", resultado: "" });

  async function act(fn: () => Promise<unknown>, ok?: string) {
    setMsg(null);
    try {
      await fn();
      if (ok) setMsg(ok);
      await reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }
  const post = (path: string, body?: unknown) => api(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
  const patch = (body: unknown) => api(`/api/leads/${id}`, { method: "PATCH", body: JSON.stringify(body) });

  if (error) return <ErrorBox error={error} />;
  if (!lead) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  const t = lead.titular;
  const est = lead.cadastro_cnpj;
  const dias = diasAte(lead.prazo_ate);
  const podeProspectar = ["aprovado", "contatado", "convertido"].includes(lead.status);

  return (
    <>
      <PageHeader title={t.nome_original}
        description={`${t.tipo_provavel} · ${t.uf ?? "UF não informada"} · ${t.pais ?? ""}${t.cnpj ? ` · CNPJ ${t.cnpj}` : ""}${lead.segmento ? ` · ${lead.segmento}` : ""}`}>
        <div className="flex flex-wrap items-center gap-2">
          {lead.prioridade && <Badge variant={prioridadeVariant[lead.prioridade]}>Prioridade {lead.prioridade} · {lead.score}</Badge>}
          <Badge variant="outline">{leadStatusLabel[lead.status] ?? lead.status}</Badge>
          {lead.precisa_revisao ? <Badge variant="destructive">Revisão humana pendente</Badge> : <Badge variant="secondary">Revisado</Badge>}
        </div>
      </PageHeader>
      {msg && <div className="mb-4 rounded-md border bg-muted/40 p-3 text-sm">{msg}</div>}
      {lead.motivo_descarte && <div className="mb-4 rounded-md border p-3 text-sm">Descartado: {lead.motivo_descarte}</div>}

      <div className="grid grid-cols-1 gap-6">
        <Section title="Decisão" description="Nada é enviado automaticamente. A prospecção só é registrada depois da aprovação.">
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => act(() => patch({ status: "aprovado", revisado: true }), "Lead aprovado.")}>
              <Check className="size-4" /> Aprovar para prospecção
            </Button>
            <Button variant="outline" onClick={() => act(() => patch({ revisado: true }), "Marcado como revisado.")}>Marcar revisado</Button>
            <Select value={lead.status} onChange={(v) => v !== "descartado" && act(() => patch({ status: v }))}
              options={Object.fromEntries(Object.entries(leadStatusLabel).filter(([k]) => k !== "descartado"))} />
            <Input placeholder="Motivo do descarte" value={motivo} onChange={(e) => setMotivo(e.target.value)} className="w-56" />
            <Button variant="outline" disabled={!motivo}
              onClick={() => act(() => patch({ status: "descartado", motivo_descarte: motivo, revisado: true }), "Lead descartado.")}>
              <X className="size-4" /> Descartar
            </Button>
            <Button variant="ghost" className="text-destructive"
              onClick={() => confirm("Registrar opt-out (LGPD) deste titular? O lead será descartado e não poderá ser prospectado.") &&
                act(() => post("/api/optout", { tipo: "titular", lead_id: Number(id), motivo: "solicitado" }), "Opt-out registrado.")}>
              Opt-out do titular (LGPD)
            </Button>
          </div>
          {lead.revisoes?.length > 0 && (
            <ul className="mt-4 space-y-1 text-sm">
              {lead.revisoes.map((r: any) => <li key={r.id} className="rounded-md bg-amber-50 p-2">⚠ {r.motivo}</li>)}
            </ul>
          )}
        </Section>

        <WhatsappCard lead={lead} podeProspectar={podeProspectar} onChange={reload} />

        {lead.servicos?.length > 0 && (
          <Section title="Serviço a oferecer" description="O titular deste lead SOFREU a oposição ou teve o pedido indeferido. Quem se opôs é só informação complementar.">
            <div className="space-y-3">
              {lead.servicos.map((o: Oportunidade) => (
                <div key={o.id} className={cn("rounded-xl border p-3", o.situacao_processual === "historico" && "opacity-75")} style={{ boxShadow: `inset 3px 0 0 ${SERVICO[o.servico].hex}` }}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={cn("rounded-full px-2 py-0.5 text-xs font-semibold", SERVICO[o.servico].classe)}>{SERVICO[o.servico].rotulo}</span>
                    {o.classificacao && <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", CLASSE[o.classificacao].classe)} title={CLASSE[o.classificacao].dica}>{CLASSE[o.classificacao].rotulo}</span>}
                    <span className="font-mono text-xs">{o.numero_processo}</span>
                    <span className="text-xs text-muted-foreground">{o.marca_nome ?? "marca não informada"} · {TIPO_DECISAO[o.tipo_decisao]} · RPI {o.rpi_numero} ({fmtDay(o.data_publicacao)}, {o.despacho_codigo})</span>
                  </div>
                  <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                    <div><dt className="inline text-muted-foreground">Prazo estimado: </dt><dd className="inline font-medium">{o.prazo_fim ? fmtDay(o.prazo_fim) : "a validar"}</dd>
                      <span className={cn("ml-2 text-xs", PRAZO[o.prazo_status].classe)}>{textoPrazo(o)}</span></div>
                    <div><dt className="inline text-muted-foreground">{o.servico === "manifestacao_oposicao" ? "Manifestação" : "Recurso"}: </dt>
                      <dd className="inline font-medium">{MEDIDA[o.medida_status]}</dd>{o.medida_protocolo && <span className="ml-1 text-xs text-muted-foreground">protocolo {o.medida_protocolo} de {fmtDay(o.medida_data)}</span>}</div>
                    {o.servico === "manifestacao_oposicao" && <div><dt className="inline text-muted-foreground">Quem se opôs: </dt><dd className="inline">{o.opositor_nome ?? "ainda não identificado (a RPI não informa)"}</dd>
                      {o.oposicao_protocolo && <span className="ml-1 text-xs text-muted-foreground">oposição {o.oposicao_protocolo} de {fmtDay(o.oposicao_data)}</span>}</div>}
                    {o.decisao_posterior && <div><dt className="inline text-muted-foreground">Decisão posterior: </dt><dd className="inline">{o.decisao_posterior}</dd></div>}
                    {o.validacao_juridica && <div className="text-orange-700 dark:text-orange-300 sm:col-span-2">Necessita validação jurídica: {o.validacao_motivo}</div>}
                    {o.fundamentacao && <div className="sm:col-span-2"><dt className="text-muted-foreground">Fundamentação publicada</dt><dd className="line-clamp-3 text-xs">{o.fundamentacao}</dd></div>}
                  </dl>
                  {o.classificacao_motivos?.length > 0 && <ul className="mt-2 flex flex-wrap gap-1.5">{o.classificacao_motivos.map((m) => <li key={m} className="rounded-md bg-muted px-2 py-0.5 text-[11px]">{m}</li>)}</ul>}
                  <details className="mt-2 text-[11px] text-muted-foreground"><summary className="cursor-pointer">Fontes</summary>
                    <p>Prazo: {o.prazo_fonte}</p>{o.medida_fonte && <p>Medida: {o.medida_fonte}</p>}{o.opositor_fonte && <p>Opositor: {o.opositor_fonte}</p>}
                  </details>
                </div>
              ))}
              {lead.peticoes?.length > 0 && (
                <details className="text-sm"><summary className="cursor-pointer text-xs font-medium text-muted-foreground">Petições do processo no pePI ({lead.peticoes.length})</summary>
                  <ul className="mt-2 divide-y rounded-lg border text-xs">
                    {lead.peticoes.map((pt: { protocolo: string; numero_processo: string; data: string | null; servico: string | null; descricao: string | null; cliente: string | null }) => (
                      <li key={pt.protocolo} className="flex flex-wrap gap-x-3 px-3 py-1.5"><span className="font-mono">{pt.numero_processo}</span><span className="font-mono">{pt.protocolo}</span>
                        <span>{fmtDay(pt.data)}</span><span className="font-medium">{pt.servico} {pt.descricao}</span><span className="text-muted-foreground">{pt.cliente}</span></li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </Section>
        )}

        <Section title="Processos" description="Número, marca, despacho, situação e procurador, com a fonte de cada dado">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Processo</TableHead><TableHead>Marca</TableHead><TableHead>Último despacho (RPI)</TableHead>
                <TableHead>Situação (INPI)</TableHead><TableHead>Procurador</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lead.processos.map((p: any) => (
                <TableRow key={p.numero_processo} className="align-top">
                  <TableCell className="font-mono">{p.numero_processo}</TableCell>
                  <TableCell>{p.marca_nome ?? <span className="text-muted-foreground">não informada</span>}
                    <div className="text-xs text-muted-foreground">{p.classes_nice?.length ? `Nice ${p.classes_nice.join(", ")}` : ""}</div>
                  </TableCell>
                  <TableCell className="max-w-80 whitespace-normal text-sm">
                    {p.ultimo_despacho ? <>
                      <span className="font-mono text-xs">{p.ultimo_despacho.despacho_codigo}</span> {p.ultimo_despacho.despacho_nome}
                      <div className="text-xs text-muted-foreground">RPI {p.ultimo_despacho.rpi} · {fmtDay(p.ultimo_despacho.data_publicacao)}</div>
                      {p.ultimo_despacho.texto_complementar && <div className="mt-1 line-clamp-3 text-xs">{p.ultimo_despacho.texto_complementar}</div>}
                    </> : "—"}
                  </TableCell>
                  <TableCell className="max-w-56 whitespace-normal text-sm">
                    {p.situacao_atual ?? "—"}
                    {p.ultima_verificacao && (
                      <a href={p.ultima_verificacao.fonte_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-muted-foreground underline">
                        consultado em {fmtDate(p.ultima_verificacao.consultado_em)} <ExternalLink className="size-3" />
                      </a>
                    )}
                  </TableCell>
                  <TableCell className="text-sm" title={p.procurador_fonte ?? ""}>
                    {p.procurador_nome ?? procuradorLabel[p.procurador_status]}
                    <div className="text-xs text-muted-foreground">{p.procurador_fonte ? `fonte: ${p.procurador_fonte}` : ""}</div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Classificação comercial"
            actions={<Button size="sm" variant="outline" onClick={() => act(() => post(`/api/leads/${id}/summary`), "Resumo será refeito em instantes.")}>
              <Sparkles className="size-4" /> Refazer resumo</Button>}>
            <div className="space-y-3 text-sm">
              <p><span className="text-muted-foreground">Categoria:</span> {lead.categoria_principal ? categoriaLabel[lead.categoria_principal] : "—"}
                {" · "}<span className="text-muted-foreground">Prazo estimado:</span>{" "}
                <span className={dias !== null && dias <= 15 ? "font-medium text-destructive" : ""}>{fmtDay(lead.prazo_ate)}{dias !== null ? ` (${dias} dias)` : ""}</span></p>
              {lead.resumo ? <p>{lead.resumo}</p> : <Empty>Resumo ainda não gerado.</Empty>}
              {lead.sugestao_abordagem && <p className="rounded-md bg-muted p-3">{lead.sugestao_abordagem}</p>}
              {lead.resumo_gerado_por && <p className="text-xs text-muted-foreground">Texto: {lead.resumo_gerado_por === "modelo-padrao" ? "modelo fixo (sem IA)" : lead.resumo_gerado_por}</p>}
              <details className="text-xs">
                <summary className="cursor-pointer text-muted-foreground">Como o score foi calculado</summary>
                <ul className="mt-2 space-y-0.5">
                  {Object.entries(lead.score_detalhes ?? {}).map(([k, v]) => (
                    <li key={k} className="flex justify-between"><span>{SCORE_LABEL[k] ?? k}</span><span className="tabular-nums">{Number(v) > 0 ? "+" : ""}{String(v)}</span></li>
                  ))}
                </ul>
              </details>
            </div>
          </Section>

          <Section title="Titular e cadastro CNPJ" description={t.cnpj_fonte ?? "Fonte: dados abertos CNPJ da Receita Federal"}>
            {est ? (
              <div className="space-y-1 text-sm">
                <p><span className="text-muted-foreground">Razão social:</span> {est.razao_social}</p>
                <p><span className="text-muted-foreground">Nome fantasia:</span> {est.nome_fantasia ?? "—"}</p>
                <p><span className="text-muted-foreground">Situação:</span> {SITUACAO_CNPJ[est.situacao_cadastral] ?? est.situacao_cadastral} · desde {fmtDay(est.data_inicio)}</p>
                <p><span className="text-muted-foreground">CNAE:</span> {est.cnae_principal} · <span className="text-muted-foreground">Porte:</span> {est.porte ?? "—"}</p>
                <p><span className="text-muted-foreground">Endereço:</span> {[est.logradouro, est.numero, est.bairro, est.uf, est.cep].filter(Boolean).join(", ")}</p>
                <p className="text-xs text-muted-foreground">Base de {est.mes_referencia} · confiança do vínculo {t.cnpj_confianca ?? "—"}</p>
              </div>
            ) : t.cnpj_status === "ambiguo" ? (
              <div className="space-y-2 text-sm">
                <p>Há mais de uma empresa com este nome. Escolha a correta:</p>
                {t.cnpj_candidatos.map((c: any) => (
                  <div key={c.cnpj} className="flex items-center justify-between rounded-md border p-2">
                    <span>{c.cnpj} · {c.fantasia ?? c.razao_social} · {c.uf} · {SITUACAO_CNPJ[c.situacao] ?? c.situacao}</span>
                    <Button size="sm" variant="outline" onClick={() => act(() => post(`/api/holders/${t.id}/cnpj`, { cnpj: c.cnpj }))}>É este</Button>
                  </div>
                ))}
                <Button size="sm" variant="ghost" onClick={() => act(() => post(`/api/holders/${t.id}/cnpj`, { nenhum: true }))}>Nenhum é o titular</Button>
              </div>
            ) : (
              <Empty>{t.cnpj_status === "nao_encontrado" ? "Nenhum CNPJ com este nome na UF informada (possível pessoa física)." : "Ainda não cruzado com a base da Receita."}</Empty>
            )}
          </Section>
        </div>

        <Section title="Dados comerciais e fontes" description="Cada contato aponta para a página ou cadastro de onde veio. Encontrado não é o mesmo que verificado."
          actions={<Button size="sm" variant="outline" onClick={() => act(() => post(`/api/leads/${id}/research`), "Pesquisa enfileirada.")}>
            <Search className="size-4" /> Pesquisar agora</Button>}>
          {lead.contatos.length === 0 ? (
            <Empty>
              Nenhum contato ainda.{" "}
              {!lead.procurador_confirmado
                ? "A busca automática começa depois que o INPI confirma a ausência de procurador."
                : lead.pesquisas.length === 0
                  ? "A leitura gratuita dos sites oficiais roda a cada hora; use também a busca assistida abaixo."
                  : "Nenhum site oficial com vínculo comprovado foi encontrado. Use a busca assistida abaixo"
                    + (ops && !ops.ia_configurada ? " ou ligue a base CNPJ na tela Operação." : ".")}
            </Empty>
          ) : (
            <ul className="divide-y text-sm">
              {lead.contatos.map((c: any) => (
                <li key={c.id} className="flex items-start justify-between gap-4 py-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{TIPOS_CONTATO[c.tipo as keyof typeof TIPOS_CONTATO] ?? c.tipo}:</span>
                      <span className={c.verificacao === "invalido" ? "line-through text-muted-foreground" : ""}>{c.valor}</span>
                      <Badge variant={c.verificacao === "verificado_humano" ? "default" : c.verificacao === "dominio_ok" ? "secondary" : c.verificacao === "invalido" ? "destructive" : "outline"}>
                        {verificacaoLabel[c.verificacao]}</Badge>
                      <Badge variant="outline">{c.fonte_tipo === "receita" ? "Receita" : c.fonte_tipo === "manual" ? "Manual" : "Web"}</Badge>
                    </div>
                    {c.fonte_url?.startsWith("http") ? (
                      <a href={c.fonte_url} target="_blank" rel="noreferrer" className="break-all text-xs text-muted-foreground underline">{c.fonte_url}</a>
                    ) : <span className="text-xs text-muted-foreground">{c.fonte_url}</span>}
                    {c.fonte_trecho && <blockquote className="mt-1 border-l-2 pl-2 text-xs text-muted-foreground">{c.fonte_trecho}</blockquote>}
                    {c.observacao && <p className="mt-1 text-xs">{c.observacao}</p>}
                    {c.checagem?.motivo && <p className="mt-1 text-xs text-destructive">{c.checagem.motivo}</p>}
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button size="sm" variant="outline" title="Confirmei este contato"
                      onClick={() => act(() => post(`/api/contacts/${c.id}/verify`, { verificacao: "verificado_humano" }))}><Check className="size-4" /></Button>
                    <Button size="sm" variant="outline" title="Contato errado"
                      onClick={() => act(() => post(`/api/contacts/${c.id}/verify`, { verificacao: "invalido" }))}><X className="size-4" /></Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4 border-t pt-4">
            <BuscaAssistida titular={t} processos={lead.processos} cnpj={t.cnpj} fantasia={est?.nome_fantasia} />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Select value={novo.tipo} onChange={(v) => setNovo({ ...novo, tipo: v })} options={TIPOS_CONTATO} />
            <Input placeholder="Valor" value={novo.valor} onChange={(e) => setNovo({ ...novo, valor: e.target.value })} className="w-56" />
            <Input placeholder="Fonte (URL ou 'ligação em 12/11')" value={novo.fonte_url} onChange={(e) => setNovo({ ...novo, fonte_url: e.target.value })} className="w-72" />
            <Button variant="outline" disabled={!novo.valor || novo.fonte_url.length < 4}
              onClick={() => act(() => post(`/api/leads/${id}/contacts`, novo), "Contato incluído.").then(() => setNovo({ tipo: "email", valor: "", fonte_url: "" }))}>
              Incluir contato</Button>
          </div>
        </Section>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Histórico de prospecção" description={podeProspectar ? "Registre aqui cada contato feito por você." : "Aprove o lead para registrar prospecções."}>
            {podeProspectar && (
              <div className="mb-4 flex flex-wrap gap-2">
                <Select value={prosp.canal} onChange={(v) => setProsp({ ...prosp, canal: v })}
                  options={{ email: "E-mail", telefone: "Telefone", whatsapp: "WhatsApp", presencial: "Presencial", outro: "Outro" }} />
                <Select value={prosp.contact_id} onChange={(v) => setProsp({ ...prosp, contact_id: v })} placeholder="Contato usado"
                  options={Object.fromEntries(lead.contatos.filter((c: any) => c.verificacao !== "invalido").map((c: any) => [String(c.id), `${c.tipo}: ${c.valor}`]))} />
                <Input placeholder="Resultado" value={prosp.resultado} onChange={(e) => setProsp({ ...prosp, resultado: e.target.value })} className="w-48" />
                <Button variant="outline" onClick={() => act(() => post(`/api/leads/${id}/outreach`, {
                  canal: prosp.canal, contact_id: prosp.contact_id ? Number(prosp.contact_id) : null, resultado: prosp.resultado || null,
                }), "Prospecção registrada.")}>Registrar</Button>
              </div>
            )}
            {lead.prospeccao.length === 0 ? <Empty>Nenhum contato comercial registrado.</Empty> : (
              <Table><TableBody>
                {lead.prospeccao.map((o: any) => (
                  <TableRow key={o.id}>
                    <TableCell>{fmtDate(o.executado_em)}</TableCell><TableCell>{o.canal}</TableCell>
                    <TableCell className="text-xs">{o.contato_valor ?? "—"}</TableCell><TableCell>{o.resultado ?? "—"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">por {o.executado_por}</TableCell>
                  </TableRow>
                ))}
              </TableBody></Table>
            )}
          </Section>

          <Section title="Histórico de pesquisas">
            {lead.pesquisas.length === 0 ? <Empty>Nenhuma pesquisa executada.</Empty> : (
              <Table><TableBody>
                {lead.pesquisas.map((r: any) => (
                  <TableRow key={r.id} className="align-top">
                    <TableCell>{fmtDate(r.iniciado_em)}</TableCell>
                    <TableCell>{r.status}<div className="text-xs text-muted-foreground">{r.buscas_web} busca(s)</div></TableCell>
                    <TableCell className="max-w-64 whitespace-normal text-xs">{(r.consultas ?? []).join(" · ")}</TableCell>
                    <TableCell className="tabular-nums">US$ {Number(r.custo_usd).toFixed(3)}</TableCell>
                  </TableRow>
                ))}
              </TableBody></Table>
            )}
          </Section>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Notas">
            <div className="mb-3 flex gap-2">
              <Textarea placeholder="Observação interna" value={nota} onChange={(e) => setNota(e.target.value)} />
              <Button variant="outline" disabled={!nota.trim()} onClick={() => act(() => post(`/api/leads/${id}/notes`, { texto: nota })).then(() => setNota(""))}>Salvar</Button>
            </div>
            {lead.notas.map((n: any) => (
              <div key={n.id} className="border-t py-2 text-sm"><p>{n.texto}</p><p className="text-xs text-muted-foreground">{n.autor} · {fmtDate(n.em)}</p></div>
            ))}
          </Section>

          <Section title="Histórico de alterações" description="Trilha de auditoria do lead"
            actions={<Button size="icon" variant="ghost" onClick={() => reload()}><RefreshCw className="size-4" /></Button>}>
            <Table><TableBody>
              {lead.historico.map((h: any) => (
                <TableRow key={h.id}>
                  <TableCell className="text-xs">{fmtDate(h.em)}</TableCell><TableCell className="text-xs">{h.acao}</TableCell>
                  <TableCell className="text-xs">{h.status_antes && h.status_antes !== h.status_depois ? `${h.status_antes} → ${h.status_depois}` : h.status_depois}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{h.ator}</TableCell>
                </TableRow>
              ))}
            </TableBody></Table>
          </Section>
        </div>
      </div>
    </>
  );
}
