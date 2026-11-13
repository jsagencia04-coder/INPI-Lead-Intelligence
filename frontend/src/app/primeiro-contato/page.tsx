"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Check, CheckCircle2, ExternalLink, FileSignature, Loader2, MessageCircle, Send, ShieldAlert, ShieldCheck, Sparkles, X, XCircle,
} from "lucide-react";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { Select } from "@/components/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/components/use-api";
import { api } from "@/lib/api";
import { fmtDate, fmtDay } from "@/lib/format";
import { CLASSE, SERVICO, TIPO_DECISAO, type Classe, type Servico } from "@/lib/servicos";
import { cn } from "@/lib/utils";

type Linha = {
  lead_id: number; titular: string; geo_uf: string | null; geo_municipio: string | null; classe_principal: Classe | null;
  servico: Servico | null; tipo_decisao: keyof typeof TIPO_DECISAO | null; numero_processo: string | null; marca_nome: string | null;
  data_publicacao: string | null; prazo_fim: string | null; contact_id: number; whatsapp: string; wa_nivel: string | null;
  origem_tipo: string | null; origem_url: string | null; consentimento: string | null;
  rascunho: { id: number; status: string; versao: number; aprovado_por: string | null } | null; contato_status: string | null;
};
type Rascunho = {
  id: number; lead_id: number; contact_id: number; numero: string; canal: "evolution" | "manual" | "meta"; conteudo: string;
  conteudo_hash: string; versao: number; status: string; gerado_por: string; aprovado_por: string | null; aprovado_em: string | null;
  rejeitado_por: string | null; motivo: string | null; updated_at: string;
};
type Detalhe = {
  lead: { id: number; titular: string; geo_uf: string | null; geo_municipio: string | null; status: string };
  oportunidade: { numero_processo: string; servico: Servico; tipo_decisao: keyof typeof TIPO_DECISAO; rpi_numero: number;
    data_publicacao: string | null; prazo_fim: string | null; marca_nome: string | null; classificacao: Classe | null } | null;
  contatos: { id: number; numero: string; wa_nivel: string | null; verificacao: string; fonte_tipo: string | null; fonte_url: string | null }[];
  rascunho: Rascunho | null;
  consentimentos: { id: number; contact_id: number; status: string; metodo: string; finalidade: string; empresa_identificada: string;
    obtido_em: string; fonte_evidencia: string; revogado_em: string | null }[];
  envios: { id: number; direcao: string; modo: string; status: string; motivo: string | null; criado_por: string; criado_em: string }[];
  verificacoes: { regra: string; ok: boolean; detalhe: string }[];
  historico: { id: number; ator: string; acao: string; em: string }[];
  modo: "real" | "simulacao"; provedor: string;
};

const RASCUNHO: Record<string, { rotulo: string; classe: string }> = {
  rascunho: { rotulo: "Em revisão", classe: "bg-amber-500/15 text-amber-800" },
  aprovado: { rotulo: "Aprovado", classe: "bg-emerald-500/15 text-emerald-700" },
  rejeitado: { rotulo: "Rejeitado", classe: "bg-zinc-500/15 text-zinc-600" },
  enviado: { rotulo: "Enviado", classe: "bg-sky-500/15 text-sky-700" },
};
const ENVIO: Record<string, string> = {
  simulada: "Simulado", na_fila: "Na fila", aceita: "Aceito pela Evolution", enviada: "Enviado", entregue: "Entregue", lida: "Lido",
  falhou: "Falhou", bloqueada: "Bloqueado", cancelada: "Cancelado", reconciliar: "Conferir no celular", recebida: "Respondeu",
};
const CONSENT: Record<string, string> = { ativo: "Autorizado", revogado: "Revogado", expirado: "Expirado" };

function Painel({ leadId, onMudou }: { leadId: number; onMudou: () => void }) {
  const { data: d, error, reload } = useApi<Detalhe>(`/api/primeiro-contato/${leadId}`);
  const [texto, setTexto] = useState("");
  const [motivo, setMotivo] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const r = d?.rascunho && ["rascunho", "aprovado"].includes(d.rascunho.status) ? d.rascunho : null;
  useEffect(() => { setTexto(r?.conteudo ?? ""); }, [r?.id, r?.versao]); // eslint-disable-line react-hooks/exhaustive-deps

  const agir = async (fn: () => Promise<unknown>, ok: string) => {
    setOcupado(true); setErro(null); setMsg(null);
    try { await fn(); setMsg(ok); await reload(); onMudou(); } catch (e) { setErro(e instanceof Error ? e.message : String(e)); } finally { setOcupado(false); }
  };
  const post = (p: string, body?: unknown) => api(p, { method: "POST", body: body ? JSON.stringify(body) : undefined });
  if (error) return <ErrorBox error={error} />;
  if (!d) return <div className="h-96 animate-pulse rounded-xl bg-muted" />;
  const alterado = r && texto !== r.conteudo;
  const pendentes = d.verificacoes.filter((v) => !v.ok);
  const podeEnviar = r?.status === "aprovado" && pendentes.length === 0;
  const op = d.oportunidade;
  const contato = d.contatos.find((c) => c.id === (r?.contact_id ?? d.contatos[0]?.id));
  const cons = d.consentimentos.find((k) => k.contact_id === contato?.id);

  return (
    <div className="space-y-4">
      <div>
        <div className="eyebrow text-primary">Lead #{d.lead.id}</div>
        <h2 className="text-lg font-semibold">{d.lead.titular}</h2>
        <p className="text-xs text-muted-foreground">{d.lead.geo_uf ?? "UF ?"}{d.lead.geo_municipio ? ` · ${d.lead.geo_municipio}` : ""} · status do lead: {d.lead.status}</p>
        {op && <p className="mt-1 text-sm">{SERVICO[op.servico].rotulo} · {op.marca_nome ?? "marca não informada"} · processo <span className="font-mono">{op.numero_processo}</span> · RPI {op.rpi_numero} ({fmtDay(op.data_publicacao)}) · prazo estimado {fmtDay(op.prazo_fim)}</p>}
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div className="rounded-xl border p-3 text-sm">
          <div className="text-[11px] text-muted-foreground">WhatsApp encontrado</div>
          <div className="font-medium">{contato?.numero ?? "—"}</div>
          <div className="text-[11px] text-muted-foreground">nível {contato?.wa_nivel ?? "—"} · origem {contato?.fonte_tipo ?? "—"} {contato?.fonte_url && <a className="underline" href={contato.fonte_url} target="_blank" rel="noreferrer">fonte</a>}</div>
        </div>
        <div className={cn("rounded-xl border p-3 text-sm", cons?.status === "ativo" ? "border-emerald-500/40" : "border-amber-500/40")}>
          <div className="text-[11px] text-muted-foreground">Autorização do destinatário (WhatsApp)</div>
          <div className="flex items-center gap-1.5 font-medium">{cons?.status === "ativo" ? <ShieldCheck className="size-4 text-emerald-600" /> : <ShieldAlert className="size-4 text-amber-600" />}{cons ? CONSENT[cons.status] : "Sem autorização registrada"}</div>
          <div className="text-[11px] text-muted-foreground">{cons ? `${cons.metodo} · ${fmtDate(cons.obtido_em)} · ${cons.fonte_evidencia}` : "Telefone público, site ou qualificação pela IA não são autorização."}</div>
        </div>
      </div>

      <div className="rounded-xl border p-3">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">Mensagem</span>
          {r && <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", RASCUNHO[r.status]?.classe)}>{RASCUNHO[r.status]?.rotulo}</span>}
          {r && <span className="text-[11px] text-muted-foreground">v{r.versao} · {r.gerado_por.startsWith("ia:") ? "sugerida pela IA" : r.gerado_por === "modelo-padrao" ? "modelo padrão" : "editada"}{r.aprovado_por ? ` · aprovada por ${r.aprovado_por}` : ""}</span>}
          <Button size="sm" variant="outline" className="ml-auto" disabled={ocupado}
            onClick={() => agir(() => post(`/api/primeiro-contato/${leadId}/rascunho`, { contact_id: contato?.id }), "Nova sugestão gerada. Revise antes de aprovar.")}>
            <Sparkles className="size-4" />{r ? "Gerar de novo" : "Gerar mensagem"}</Button>
        </div>
        {r ? (
          <>
            <Textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={8} className="text-sm" />
            <div className="mt-1 flex justify-between text-[11px] text-muted-foreground"><span>{texto.length}/1500 caracteres</span>{alterado && <span className="text-amber-700">Alterações não salvas: salve para aprovar</span>}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" variant="outline" disabled={!alterado || ocupado}
                onClick={() => agir(() => api(`/api/rascunhos/${r.id}`, { method: "PATCH", body: JSON.stringify({ conteudo: texto, versao: r.versao }) }), "Edição salva. A aprovação anterior deixou de valer.")}>Salvar edição</Button>
              <Button size="sm" disabled={!!alterado || r.status !== "rascunho" || ocupado}
                onClick={() => agir(() => post(`/api/rascunhos/${r.id}/aprovar`, { versao: r.versao, conteudo_hash: r.conteudo_hash, numero: r.numero, canal: r.canal }), "Aprovado para este número e canal.")}>
                <CheckCircle2 className="size-4" />Aprovar</Button>
              <Input placeholder="Motivo da rejeição" value={motivo} onChange={(e) => setMotivo(e.target.value)} className="h-8 w-44 text-xs" />
              <Button size="sm" variant="ghost" disabled={motivo.trim().length < 3 || ocupado}
                onClick={() => agir(() => post(`/api/rascunhos/${r.id}/rejeitar`, { motivo }), "Rascunho rejeitado: nada será enviado.")}><XCircle className="size-4" />Rejeitar</Button>
            </div>
          </>
        ) : <p className="text-sm text-muted-foreground">Nenhum rascunho em aberto. Gere uma sugestão: a IA usa só dados verificados do processo e você revisa tudo.</p>}
      </div>

      {r && (
        <div className="rounded-xl border p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold">Requisitos para enviar
            <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", d.modo === "real" ? "bg-rose-500/15 text-rose-700" : "bg-slate-500/15 text-slate-700")}>
              {d.modo === "real" ? "envio real ligado" : "simulação: nada sai do sistema"}</span></div>
          <ul className="space-y-1 text-sm">
            {d.verificacoes.map((v) => (
              <li key={v.regra} className="flex items-start gap-2">{v.ok ? <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" /> : <X className="mt-0.5 size-4 shrink-0 text-rose-600" />}<span className={v.ok ? "" : "text-rose-700 dark:text-rose-300"}>{v.detalhe}</span></li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button disabled={!podeEnviar || ocupado}
              onClick={() => confirm(`${d.modo === "real" ? "ENVIAR DE VERDADE" : "Simular o envio"} para ${r.numero}? Uma única mensagem; as respostas ficam com você no WhatsApp Business.`) &&
                agir(() => post(`/api/rascunhos/${r.id}/enviar`), d.modo === "real" ? "Envio solicitado: acompanhe o status abaixo." : "Envio simulado registrado (nada saiu).")}>
              {ocupado ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}{d.modo === "real" ? "Enviar" : "Simular envio"}</Button>
            <Button variant="outline" disabled={ocupado}
              onClick={() => agir(async () => { const x = await post(`/api/rascunhos/${r.id}/abrir-whatsapp`) as { url: string }; window.open(x.url, "_blank", "noopener"); }, "Aberto no WhatsApp. Isso não registra envio: registre a prospecção no lead depois de enviar.")}>
              <ExternalLink className="size-4" />Abrir no WhatsApp</Button>
          </div>
        </div>
      )}
      {msg && <p className="rounded-lg bg-emerald-500/10 p-2 text-sm text-emerald-800">{msg}</p>}
      {erro && <p className="rounded-lg bg-rose-500/10 p-2 text-sm text-rose-800">{erro}</p>}

      {d.envios.length > 0 && (
        <div className="rounded-xl border p-3 text-sm">
          <div className="mb-1 font-semibold">Envios e respostas</div>
          <ul className="divide-y">{d.envios.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center gap-2 py-1.5">
              <span className="font-medium">{e.direcao === "entrada" ? "Resposta recebida" : ENVIO[e.status] ?? e.status}</span>
              <span className="text-[11px] text-muted-foreground">{fmtDate(e.criado_em)} · {e.modo} · {e.criado_por}</span>
              {e.motivo && <span className="w-full text-[11px] text-muted-foreground">{e.motivo}</span>}
              {e.status === "reconciliar" && (
                <span className="flex gap-1.5">
                  <Button size="sm" variant="outline" onClick={() => agir(() => post(`/api/wa-mensagens/${e.id}/reconciliar`, { resultado: "enviada" }), "Registrado: a mensagem saiu.")}>Saiu (vi no celular)</Button>
                  <Button size="sm" variant="ghost" onClick={() => agir(() => post(`/api/wa-mensagens/${e.id}/reconciliar`, { resultado: "nao_enviada" }), "Registrado: não saiu.")}>Não saiu</Button>
                </span>
              )}
            </li>))}</ul>
          <p className="mt-1 text-[11px] text-muted-foreground">Depois do primeiro envio, a conversa é só sua, no app WhatsApp Business. O sistema não responde nem faz follow-up.</p>
        </div>
      )}

      <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Histórico de ações ({d.historico.length})</summary>
        <ul className="mt-1 space-y-0.5">{d.historico.map((h) => <li key={h.id}>{fmtDate(h.em)} · {h.acao.replaceAll("_", " ")} · {h.ator}</li>)}</ul>
      </details>
      <Link href={`/leads/${leadId}`} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">Abrir o lead no CRM <ExternalLink className="size-3" /></Link>
    </div>
  );
}

function Pagina() {
  const sp = useSearchParams();
  const [classe, setClasse] = useState(sp.get("classificacao") ?? "");
  const [situacao, setSituacao] = useState("");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number | null>(sp.get("lead") ? Number(sp.get("lead")) : null);
  const f = new URLSearchParams();
  if (classe) f.set("classificacao", classe);
  if (situacao) f.set("situacao", situacao);
  if (q.trim()) f.set("q", q.trim());
  const { data, error, reload } = useApi<Linha[]>(`/api/primeiro-contato?${f}`);
  const { data: integ } = useApi<{ modo: string; provedor: string; envio_bloqueado: boolean }>("/api/integracao-whatsapp");

  return (
    <>
      <PageHeader title="Primeiro contato" description="Uma única mensagem por titular, escrita com ajuda da IA, aprovada por uma pessoa e enviada só com autorização do destinatário. Depois, a conversa é sua no WhatsApp Business.">
        <Link href="/integracao-whatsapp" className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium",
          integ?.envio_bloqueado ? "bg-rose-500/15 text-rose-700" : integ?.modo === "real" ? "bg-emerald-500/15 text-emerald-700" : "bg-slate-500/15 text-slate-700")}>
          <MessageCircle className="size-3.5" />{integ ? (integ.envio_bloqueado ? "Envios desativados" : integ.modo === "real" ? `Envio real · ${integ.provedor}` : `Simulação · ${integ.provedor}`) : "…"}
        </Link>
      </PageHeader>
      <ErrorBox error={error} />
      <div className="surface mb-4 flex flex-wrap items-end gap-3 p-3">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Qualificação<Select value={classe} onChange={setClasse} placeholder="Todas"
          options={Object.fromEntries(Object.entries(CLASSE).map(([k, v]) => [k, v.rotulo]))} /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Revisão<Select value={situacao} onChange={setSituacao} placeholder="Todas"
          options={{ sem_rascunho: "Sem mensagem", rascunho: "Em revisão", aprovado: "Aprovada", enviado: "Enviada", rejeitado: "Rejeitada" }} /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Buscar<Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Titular, marca ou processo" className="w-60" /></label>
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <section className="surface overflow-hidden">
          <ul className="divide-y">
            {data?.map((l) => (
              <li key={l.lead_id}>
                <button onClick={() => setSel(l.lead_id)} className={cn("flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-accent/40", sel === l.lead_id && "bg-primary/5")}>
                  <span className={cn("mt-0.5 rounded-full px-2 py-0.5 text-[11px] font-medium", l.classe_principal ? CLASSE[l.classe_principal].classe : "bg-muted")}>{l.classe_principal ? CLASSE[l.classe_principal].rotulo : "—"}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{l.titular}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">{l.servico ? SERVICO[l.servico].curto : ""} · {l.marca_nome ?? "marca ?"} · {l.numero_processo} · {fmtDay(l.data_publicacao)} · {l.geo_uf ?? "UF ?"}{l.geo_municipio ? `/${l.geo_municipio}` : ""}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">{l.whatsapp} ({l.origem_tipo ?? "origem ?"}) · {l.consentimento ? CONSENT[l.consentimento] : "sem autorização"}</span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1 text-[11px]">
                    {l.rascunho ? <span className={cn("rounded-full px-2 py-0.5 font-medium", RASCUNHO[l.rascunho.status]?.classe)}>{RASCUNHO[l.rascunho.status]?.rotulo}</span> : <span className="text-muted-foreground"><FileSignature className="inline size-3" /> sem mensagem</span>}
                    {l.contato_status && <span className="text-muted-foreground">{ENVIO[l.contato_status] ?? l.contato_status}</span>}
                  </span>
                </button>
              </li>
            ))}
            {data && data.length === 0 && <li className="p-8 text-center text-sm text-muted-foreground">Nenhum lead com WhatsApp encontrado nestes filtros.</li>}
          </ul>
        </section>
        <section className="surface p-4">
          {sel ? <Painel key={sel} leadId={sel} onMudou={reload} /> : <p className="py-16 text-center text-sm text-muted-foreground">Escolha um lead na lista para preparar a mensagem.</p>}
        </section>
      </div>
    </>
  );
}

export default function PrimeiroContatoPage() {
  return <Suspense><Pagina /></Suspense>;
}
