"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Eye, History, Loader2, Save } from "lucide-react";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/components/use-api";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";

/** V2.7 · Comercial → WhatsApp → Configurações de mensagens: os três modelos ficam no banco e são editados aqui. */
type Modelo = {
  id: number; codigo: string; nome: string; descricao: string; tipo_oportunidade: string; finalidade: string; texto: string;
  ativo: boolean; versao: number; atualizado_em: string; atualizado_por: string;
};
type Dados = { modelos: Modelo[]; remetente: { nome_atendente: string; empresa: string }; variaveis: Record<string, string> };
type Previa = { texto: string; alertas: string[]; exemplo: boolean; compativel: boolean };
type Hist = { id: number; versao: number; nome: string; texto: string; ativo: boolean; alterado_por: string; alterado_em: string };

const TIPO: Record<string, string> = { oposicao: "Oposição apresentada", indeferimento: "Indeferimento", institucional: "Outros casos elegíveis" };

function CartaoModelo({ m, variaveis, onSalvo }: { m: Modelo; variaveis: Record<string, string>; onSalvo: () => void }) {
  const [f, setF] = useState({ nome: m.nome, descricao: m.descricao, texto: m.texto, ativo: m.ativo });
  const [leadId, setLeadId] = useState("");
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [hist, setHist] = useState<Hist[] | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  useEffect(() => { setF({ nome: m.nome, descricao: m.descricao, texto: m.texto, ativo: m.ativo }); }, [m.versao]); // eslint-disable-line react-hooks/exhaustive-deps
  const alterado = f.nome !== m.nome || f.descricao !== m.descricao || f.texto !== m.texto || f.ativo !== m.ativo;

  const salvar = async () => {
    setOcupado(true); setMsg(null);
    try { await api(`/api/wa-modelos/${m.codigo}`, { method: "PUT", body: JSON.stringify({ ...f, versao: m.versao }) }); setMsg({ ok: true, t: "Modelo salvo. Vale para as próximas mensagens preparadas." }); onSalvo(); }
    catch (e) { setMsg({ ok: false, t: e instanceof Error ? e.message : String(e) }); } finally { setOcupado(false); }
  };
  const testar = async () => {
    setOcupado(true); setMsg(null);
    try { setPrevia(await api<Previa>(`/api/wa-modelos/${m.codigo}/previa`, { method: "POST", body: JSON.stringify({ texto: f.texto, lead_id: leadId ? Number(leadId) : null }) })); }
    catch (e) { setMsg({ ok: false, t: e instanceof Error ? e.message : String(e) }); } finally { setOcupado(false); }
  };
  const inserir = (v: string) => setF({ ...f, texto: `${f.texto}{{${v}}}` });

  return (
    <section className="surface p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-primary/10 px-2 py-0.5 font-mono text-xs text-primary">{m.codigo.replace("_", " ")}</span>
        <h2 className="font-semibold">{m.nome}</h2>
        <span className="text-xs text-muted-foreground">· {TIPO[m.tipo_oportunidade]} · {m.finalidade}</span>
        <label className="ml-auto flex items-center gap-1.5 text-sm"><input type="checkbox" checked={f.ativo} onChange={(e) => setF({ ...f, ativo: e.target.checked })} />Ativo</label>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Nome<Input value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Descrição<Input value={f.descricao} onChange={(e) => setF({ ...f, descricao: e.target.value })} /></label>
      </div>
      <label className="mt-2 flex flex-col gap-1 text-xs text-muted-foreground">Texto
        <Textarea rows={10} value={f.texto} onChange={(e) => setF({ ...f, texto: e.target.value })} className="font-mono text-xs text-foreground" /></label>
      <div className="mt-1 flex flex-wrap gap-1">
        {Object.entries(variaveis).map(([k, d]) => (
          <button key={k} type="button" title={d} onClick={() => inserir(k)} className="rounded border px-1.5 py-0.5 font-mono text-[10px] hover:bg-accent">{`{{${k}}}`}</button>
        ))}
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">Identificação {m.codigo} · versão {m.versao} · alterado em {fmtDate(m.atualizado_em)} por {m.atualizado_por.replace("user:", "")} · {f.texto.length}/1500</p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <Button onClick={salvar} disabled={!alterado || ocupado}>{ocupado ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}Salvar</Button>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Lead para a prévia (opcional)<Input value={leadId} onChange={(e) => setLeadId(e.target.value.replace(/\D/g, ""))} placeholder="nº do lead" className="h-9 w-32" /></label>
        <Button variant="outline" onClick={testar} disabled={ocupado}><Eye className="size-4" />Testar prévia</Button>
        <Button variant="ghost" onClick={async () => setHist(hist ? null : await api<Hist[]>(`/api/wa-modelos/${m.codigo}/historico`))}><History className="size-4" />Versões</Button>
      </div>
      {msg && <p className={cn("mt-2 rounded-lg p-2 text-sm", msg.ok ? "bg-emerald-500/10 text-emerald-800" : "bg-rose-500/10 text-rose-800")}>{msg.t}</p>}
      {previa && (
        <div className="mt-3 rounded-xl border bg-muted/30 p-3">
          <div className="mb-1 text-xs font-semibold">Pré-visualização {previa.exemplo ? "(dados de exemplo)" : `(lead nº ${leadId})`}{!previa.compativel && <span className="ml-1 text-amber-700">· este modelo não combina com a oportunidade deste lead</span>}</div>
          <p className="whitespace-pre-wrap text-sm">{previa.texto}</p>
          {previa.alertas.length > 0 && <ul className="mt-2 space-y-0.5 text-xs text-amber-900">{previa.alertas.map((a) => <li key={a} className="flex gap-1"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{a}</li>)}</ul>}
          <p className="mt-1 text-[11px] text-muted-foreground">A prévia não grava nada nem envia mensagem.</p>
        </div>
      )}
      {hist && (
        <ul className="mt-3 space-y-1 text-xs">{hist.map((h) => (
          <li key={h.id}><details><summary className="cursor-pointer">v{h.versao} · {fmtDate(h.alterado_em)} · {h.alterado_por.replace("user:", "")}{h.ativo ? "" : " · inativo"}</summary><p className="whitespace-pre-wrap rounded bg-muted/40 p-2">{h.texto}</p></details></li>
        ))}</ul>
      )}
    </section>
  );
}

export default function ConfiguracoesMensagensPage() {
  const { data, error, reload } = useApi<Dados>("/api/wa-modelos");
  const [rem, setRem] = useState({ nome_atendente: "", empresa: "" });
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { if (data) setRem(data.remetente); }, [data]);
  return (
    <>
      <PageHeader title="Configurações de mensagens" description="Comercial → WhatsApp. Três modelos de primeira mensagem, guardados no banco: edite sem publicar uma nova versão do sistema. Os modelos adequam a mensagem à oportunidade; não há rotação nem variação artificial." />
      <ErrorBox error={error} />
      {data && (
        <div className="space-y-6">
          <section className="surface flex flex-wrap items-end gap-3 p-4">
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">Seu nome {"{{nome_atendente}}"}<Input value={rem.nome_atendente} onChange={(e) => setRem({ ...rem, nome_atendente: e.target.value })} className="w-64" /></label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">Sua empresa {"{{empresa}}"}<Input value={rem.empresa} onChange={(e) => setRem({ ...rem, empresa: e.target.value })} className="w-72" /></label>
            <Button variant="outline" onClick={async () => { try { await api("/api/wa-modelos-remetente", { method: "PUT", body: JSON.stringify(rem) }); setMsg("Remetente salvo."); reload(); } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); } }}><Save className="size-4" />Salvar remetente</Button>
            {msg && <span className="text-sm text-muted-foreground">{msg}</span>}
            <p className="w-full text-[11px] text-muted-foreground">Variável sem valor nunca vira texto inventado: aparece como lacuna entre colchetes, gera alerta e impede a aprovação até ser preenchida.</p>
          </section>
          {data.modelos.map((m) => <CartaoModelo key={m.codigo} m={m} variaveis={data.variaveis} onSalvo={reload} />)}
        </div>
      )}
    </>
  );
}
