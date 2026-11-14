"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle, Check, CheckCircle2, CircleDashed, ExternalLink, Loader2, Send, ShieldAlert, ShieldCheck, Sparkles, X, XCircle,
} from "lucide-react";
import { ErrorBox } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/components/use-api";
import { api } from "@/lib/api";
import { fmtDate, fmtDay } from "@/lib/format";
import { SERVICO, TIPO_DECISAO, type Classe, type Servico } from "@/lib/servicos";
import { cn } from "@/lib/utils";

/** V2.5/V2.7 · Painel de revisão e envio do primeiro contato (usado no Primeiro contato e nos detalhes do lead).
 *  O envio é feito pelo backend, nesta mesma tela: nada de nova guia, wa.me ou WhatsApp Web no modo Evolution. */

type Rascunho = {
  id: number; lead_id: number; contact_id: number; numero: string; canal: "evolution" | "manual" | "meta"; conteudo: string;
  conteudo_hash: string; versao: number; status: string; gerado_por: string; aprovado_por: string | null; aprovado_em: string | null;
  rejeitado_por: string | null; motivo: string | null; updated_at: string; finalidade: string | null; alertas: string[];
};
type Modelo = { codigo: string; nome: string; descricao: string; tipo_oportunidade: string; finalidade: string; ativo: boolean; versao: number; compativel: boolean };
type Envio = {
  id: number; direcao: string; modo: string; status: string; motivo: string | null; numero: string; numero_processo: string | null;
  criado_por: string; criado_em: string; aceita_em: string | null; entregue_em: string | null; lida_em: string | null; falhou_em: string | null;
  wa_message_id: string | null; erro_codigo: string | null; corpo: string | null; modelo_codigo: string | null; modelo_nome: string | null;
  aprovado_por: string | null; aprovado_em: string | null; finalidade: string | null;
};
type Detalhe = {
  lead: { id: number; titular: string; geo_uf: string | null; geo_municipio: string | null; status: string };
  oportunidade: { numero_processo: string; servico: Servico; tipo_decisao: keyof typeof TIPO_DECISAO; rpi_numero: number;
    data_publicacao: string | null; prazo_fim: string | null; marca_nome: string | null; classificacao: Classe | null } | null;
  contatos: { id: number; numero: string; wa_nivel: string | null; verificacao: string; fonte_tipo: string | null; fonte_url: string | null }[];
  rascunho: Rascunho | null;
  consentimentos: { id: number; contact_id: number; status: string; metodo: string; obtido_em: string; fonte_evidencia: string }[];
  envios: Envio[];
  verificacoes: { regra: string; ok: boolean; detalhe: string }[];
  historico: { id: number; ator: string; acao: string; em: string }[];
  modo: "real" | "simulacao"; provedor: string;
  modelos: Modelo[]; modelo_sugerido: string; modelo_rascunho: { codigo: string; nome: string; versao: number } | null;
};
type Mensagem = { id: number; status: string; motivo: string | null; wa_message_id: string | null; entregue_em: string | null; lida_em: string | null };

const RASCUNHO: Record<string, { rotulo: string; classe: string }> = {
  rascunho: { rotulo: "Em revisão", classe: "bg-amber-500/15 text-amber-800" },
  aprovado: { rotulo: "Aprovado", classe: "bg-emerald-500/15 text-emerald-700" },
  rejeitado: { rotulo: "Rejeitado", classe: "bg-zinc-500/15 text-zinc-600" },
  enviado: { rotulo: "Enviado", classe: "bg-sky-500/15 text-sky-700" },
};
export const ENVIO: Record<string, string> = {
  simulada: "Simulado (nada saiu)", na_fila: "Na fila", aceita: "Aceita pelo provedor", enviada: "Enviada", entregue: "Entregue", lida: "Lida",
  falhou: "Falha no envio", bloqueada: "Bloqueada", cancelada: "Cancelada", reconciliar: "Conferir no celular", recebida: "Respondeu",
};
const CONSENT: Record<string, string> = { ativo: "Autorizado", revogado: "Revogado", expirado: "Expirado" };

/** Estados visuais do botão (seção 5 do escopo). "Entregue" só com o evento do WhatsApp. */
type Fase = "pronto" | "aguardando" | "enviando" | "aceita" | "entregue" | "falha" | "incerto" | "simulada";
const FASE: Record<Fase, { rotulo: string; classe: string }> = {
  pronto: { rotulo: "Enviar mensagem", classe: "" },
  aguardando: { rotulo: "Aguardando envio...", classe: "" },
  enviando: { rotulo: "Enviando mensagem...", classe: "" },
  aceita: { rotulo: "Mensagem aceita pelo provedor", classe: "bg-sky-600 hover:bg-sky-600" },
  entregue: { rotulo: "Mensagem entregue", classe: "bg-emerald-600 hover:bg-emerald-600" },
  falha: { rotulo: "Falha no envio", classe: "bg-rose-600 hover:bg-rose-600" },
  incerto: { rotulo: "Resultado incerto: confira no celular", classe: "bg-amber-600 hover:bg-amber-600" },
  simulada: { rotulo: "Envio simulado (nada saiu)", classe: "bg-slate-600 hover:bg-slate-600" },
};
const faseDo = (st: string): Fase =>
  st === "entregue" || st === "lida" ? "entregue" : st === "aceita" || st === "enviada" ? "aceita" : st === "simulada" ? "simulada"
    : st === "reconciliar" ? "incerto" : st === "na_fila" ? "enviando" : "falha";

const novaChave = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`);

export function PrimeiroContatoPainel({ leadId, onMudou, compacto }: { leadId: number; onMudou?: () => void; compacto?: boolean }) {
  const { data: d, error, reload } = useApi<Detalhe>(`/api/primeiro-contato/${leadId}`);
  const [texto, setTexto] = useState("");
  const [motivo, setMotivo] = useState("");
  const [modelo, setModelo] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [fase, setFase] = useState<Fase>("pronto");
  const [envio, setEnvio] = useState<Mensagem | null>(null);
  const chave = useRef<{ alvo: string; valor: string } | null>(null);
  const r = d?.rascunho && ["rascunho", "aprovado"].includes(d.rascunho.status) ? d.rascunho : null;
  useEffect(() => { setTexto(r?.conteudo ?? ""); }, [r?.id, r?.versao]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (d && !modelo) setModelo(d.modelo_rascunho?.codigo ?? d.modelo_sugerido); }, [d]); // eslint-disable-line react-hooks/exhaustive-deps

  // acompanha o envio aceito até a confirmação de entrega (webhook), sem recarregar a página
  useEffect(() => {
    if (!envio || !["aceita", "enviada", "na_fila"].includes(envio.status)) return;
    let n = 0;
    const t = setInterval(async () => {
      n += 1;
      try {
        const m = await api<Mensagem>(`/api/wa-mensagens/${envio.id}`);
        if (m.status !== envio.status) { setEnvio(m); setFase(faseDo(m.status)); reload(); }
      } catch { /* mantém o último estado */ }
      if (n >= 60) clearInterval(t);
    }, 3000);
    return () => clearInterval(t);
  }, [envio]); // eslint-disable-line react-hooks/exhaustive-deps

  const agir = async (fn: () => Promise<unknown>, ok: string) => {
    setOcupado(true); setErro(null); setMsg(null);
    try { await fn(); setMsg(ok); await reload(); onMudou?.(); } catch (e) { setErro(e instanceof Error ? e.message : String(e)); } finally { setOcupado(false); }
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
  const evolutionAtiva = d.provedor === "evolution";
  const emAndamento = ["aguardando", "enviando"].includes(fase);

  const enviar = async () => {
    if (!r) return;
    const alvo = `${r.id}:${r.versao}`;
    // mesmo clique (duplo clique, rede) = mesma chave; nova tentativa consciente após falha definitiva = nova chave
    if (chave.current?.alvo !== alvo || fase === "falha") chave.current = { alvo, valor: novaChave() };
    if (d.modo === "real" && !confirm(`Enviar AGORA, pela Evolution, para ${r.numero}? Uma única mensagem; as respostas ficam com você no WhatsApp Business.`)) return;
    setErro(null); setMsg(null); setFase("aguardando"); setOcupado(true);
    try {
      setFase("enviando");
      const m = await api<Mensagem>(`/api/rascunhos/${r.id}/enviar`, { method: "POST", body: JSON.stringify({ chave: chave.current.valor }) });
      setEnvio(m); setFase(faseDo(m.status));
      if (m.motivo && ["falhou", "bloqueada", "reconciliar"].includes(m.status)) setErro(m.motivo);
      await reload(); onMudou?.();
    } catch (e) {
      setFase("falha"); setErro(e instanceof Error ? e.message : String(e));
    } finally { setOcupado(false); }
  };

  return (
    <div className="space-y-4">
      {!compacto && (
        <div>
          <div className="eyebrow text-primary">Lead #{d.lead.id}</div>
          <h2 className="text-lg font-semibold">{d.lead.titular}</h2>
          <p className="text-xs text-muted-foreground">{d.lead.geo_uf ?? "UF ?"}{d.lead.geo_municipio ? ` · ${d.lead.geo_municipio}` : ""} · status do lead: {d.lead.status}</p>
          {op && <p className="mt-1 text-sm">{SERVICO[op.servico].rotulo} · {op.marca_nome ?? "marca não informada"} · processo <span className="font-mono">{op.numero_processo}</span> · RPI {op.rpi_numero} ({fmtDay(op.data_publicacao)}) · prazo estimado {fmtDay(op.prazo_fim)}</p>}
        </div>
      )}

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
        <div className="mb-2 flex flex-wrap items-end gap-2">
          <span className="text-sm font-semibold">Mensagem</span>
          {r && <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", RASCUNHO[r.status]?.classe)}>{RASCUNHO[r.status]?.rotulo}</span>}
          {r && <span className="text-[11px] text-muted-foreground">v{r.versao}{d.modelo_rascunho ? ` · ${d.modelo_rascunho.nome} (modelo v${d.modelo_rascunho.versao})` : ""}{r.finalidade ? ` · ${r.finalidade}` : ""}{r.aprovado_por ? ` · aprovada por ${r.aprovado_por}` : ""}</span>}
          <label className="ml-auto flex flex-col gap-1 text-[11px] text-muted-foreground">Modelo
            <select value={modelo} onChange={(e) => setModelo(e.target.value)} className="h-8 rounded-lg border bg-card px-2 text-xs text-foreground">
              {d.modelos.map((m) => <option key={m.codigo} value={m.codigo} disabled={!m.ativo || !m.compativel}>
                {m.codigo.replace("MODELO_", "Modelo ")} · {m.nome}{m.codigo === d.modelo_sugerido ? " (sugerido)" : ""}{!m.ativo ? " (inativo)" : !m.compativel ? " (outra finalidade)" : ""}</option>)}
            </select>
          </label>
          <Button size="sm" variant="outline" disabled={ocupado || !modelo}
            onClick={() => agir(() => post(`/api/primeiro-contato/${leadId}/rascunho`, { contact_id: contato?.id, modelo }), "Mensagem preparada com o modelo escolhido. Revise antes de aprovar.")}>
            <Sparkles className="size-4" />{r ? "Preparar de novo" : "Preparar mensagem"}</Button>
        </div>
        {r ? (
          <>
            {r.alertas?.length > 0 && (
              <ul className="mb-2 space-y-0.5 rounded-lg bg-amber-500/10 p-2 text-xs text-amber-900">
                {r.alertas.map((a) => <li key={a} className="flex gap-1.5"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{a}. Preencha a lacuna entre colchetes ou complete o cadastro.</li>)}
              </ul>
            )}
            <Textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={9} className="text-sm" />
            <div className="mt-1 flex justify-between text-[11px] text-muted-foreground"><span>{texto.length}/1500 caracteres</span>{alterado && <span className="text-amber-700">Alterações não salvas: salve para aprovar</span>}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" variant="outline" disabled={!alterado || ocupado}
                onClick={() => agir(() => api(`/api/rascunhos/${r.id}`, { method: "PATCH", body: JSON.stringify({ conteudo: texto, versao: r.versao }) }), "Edição salva. A aprovação anterior deixou de valer.")}>Salvar edição</Button>
              <Button size="sm" disabled={!!alterado || r.status !== "rascunho" || ocupado}
                onClick={() => agir(() => post(`/api/rascunhos/${r.id}/aprovar`, { versao: r.versao, conteudo_hash: r.conteudo_hash, numero: r.numero, canal: r.canal }), "Aprovado para este texto, número, canal e modelo.")}>
                <CheckCircle2 className="size-4" />Aprovar</Button>
              <Input placeholder="Motivo da rejeição" value={motivo} onChange={(e) => setMotivo(e.target.value)} className="h-8 w-44 text-xs" />
              <Button size="sm" variant="ghost" disabled={motivo.trim().length < 3 || ocupado}
                onClick={() => agir(() => post(`/api/rascunhos/${r.id}/rejeitar`, { motivo }), "Rascunho rejeitado: nada será enviado.")}><XCircle className="size-4" />Rejeitar</Button>
            </div>
          </>
        ) : <p className="text-sm text-muted-foreground">Nenhuma mensagem em aberto. Escolha o modelo (o sugerido combina com a oportunidade) e prepare: as variáveis usam só dados verdadeiros do processo.</p>}
      </div>

      {(r || envio) && (
        <div className="rounded-xl border p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold">Requisitos para enviar
            <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", d.modo === "real" ? "bg-rose-500/15 text-rose-700" : "bg-slate-500/15 text-slate-700")}>
              {d.modo === "real" ? "envio real ligado" : "simulação: nada sai do sistema"}</span></div>
          <ul className="space-y-1 text-sm">
            {d.verificacoes.map((v) => (
              <li key={v.regra} className="flex items-start gap-2">{v.ok ? <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" /> : <X className="mt-0.5 size-4 shrink-0 text-rose-600" />}<span className={v.ok ? "" : "text-rose-700 dark:text-rose-300"}>{v.detalhe}</span></li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {evolutionAtiva ? (
              <Button type="button" className={cn("min-w-56", FASE[fase].classe)} aria-live="polite"
                disabled={emAndamento || ocupado || (fase === "pronto" ? !podeEnviar : !["falha"].includes(fase) || !podeEnviar)}
                onClick={enviar}>
                {emAndamento ? <Loader2 className="size-4 animate-spin" /> : fase === "entregue" ? <CheckCircle2 className="size-4" /> : fase === "aceita" ? <CircleDashed className="size-4" /> : <Send className="size-4" />}
                {FASE[fase].rotulo}</Button>
            ) : (
              <Button variant="outline" disabled={ocupado || !r}
                onClick={() => r && agir(async () => { const x = await post(`/api/rascunhos/${r.id}/abrir-whatsapp`) as { url: string }; window.open(x.url, "_blank", "noopener"); }, "Aberto no WhatsApp. Isso não registra envio: registre a prospecção no lead depois de enviar.")}>
                <ExternalLink className="size-4" />Abrir no WhatsApp (modo manual)</Button>
            )}
            {fase === "aceita" && <span className="text-xs text-muted-foreground">Aguardando a confirmação de entrega do WhatsApp…</span>}
          </div>
        </div>
      )}
      {msg && <p className="rounded-lg bg-emerald-500/10 p-2 text-sm text-emerald-800">{msg}</p>}
      {erro && <p className="rounded-lg bg-rose-500/10 p-2 text-sm text-rose-800">{erro}</p>}

      {d.envios.length > 0 && (
        <div className="rounded-xl border p-3 text-sm">
          <div className="mb-1 font-semibold">Histórico de envios e respostas</div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-left text-muted-foreground"><tr><th className="py-1 font-medium">Data</th><th className="font-medium">Situação</th><th className="font-medium">Modelo</th><th className="font-medium">Destino</th><th className="font-medium">Aprovado por</th><th className="font-medium">Id no provedor</th></tr></thead>
              <tbody>{d.envios.map((e) => (
                <tr key={e.id} className="border-t align-top">
                  <td className="py-1 pr-2 whitespace-nowrap">{fmtDate(e.criado_em)}</td>
                  <td className="pr-2"><span className="font-medium">{e.direcao === "entrada" ? "Resposta recebida" : ENVIO[e.status] ?? e.status}</span>
                    <span className="block text-muted-foreground">{e.modo}{e.entregue_em ? ` · entregue ${fmtDate(e.entregue_em)}` : ""}{e.motivo ? ` · ${e.motivo}` : ""}{e.erro_codigo ? ` (${e.erro_codigo})` : ""}</span>
                    {e.status === "reconciliar" && (
                      <span className="mt-1 flex gap-1.5">
                        <Button size="sm" variant="outline" onClick={() => agir(() => post(`/api/wa-mensagens/${e.id}/reconciliar`, { resultado: "enviada" }), "Registrado: a mensagem saiu.")}>Saiu (vi no celular)</Button>
                        <Button size="sm" variant="ghost" onClick={() => agir(() => post(`/api/wa-mensagens/${e.id}/reconciliar`, { resultado: "nao_enviada" }), "Registrado: não saiu.")}>Não saiu</Button>
                      </span>
                    )}
                    {e.corpo && <details className="mt-0.5"><summary className="cursor-pointer text-muted-foreground">texto enviado</summary><p className="whitespace-pre-wrap">{e.corpo}</p></details>}
                  </td>
                  <td className="pr-2">{e.modelo_nome ?? "—"}</td>
                  <td className="pr-2 whitespace-nowrap">{e.numero}{e.numero_processo ? <span className="block font-mono text-muted-foreground">{e.numero_processo}</span> : null}</td>
                  <td className="pr-2">{e.aprovado_por ?? "—"}</td>
                  <td className="font-mono">{e.wa_message_id ?? "—"}</td>
                </tr>))}</tbody>
            </table>
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">Depois do primeiro envio, a conversa é só sua, no app WhatsApp Business. O sistema não responde, não faz follow-up e não inicia novo contato.</p>
        </div>
      )}

      <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Histórico de ações ({d.historico.length})</summary>
        <ul className="mt-1 space-y-0.5">{d.historico.map((h) => <li key={h.id}>{fmtDate(h.em)} · {h.acao.replaceAll("_", " ")} · {h.ator}</li>)}</ul>
      </details>
      {!compacto && <Link href={`/leads/${leadId}`} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">Abrir o lead no CRM <ExternalLink className="size-3" /></Link>}
    </div>
  );
}

/** Aviso de respostas recebidas (nada é respondido pelo sistema). */
export function AvisoRespostas() {
  const { data, reload } = useApi<{ novas: number; itens: { id: number; lead_id: number; titular: string; criado_em: string }[] }>("/api/primeiro-contato-respostas", 30000);
  if (!data?.novas) return null;
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-900">
      <CheckCircle2 className="size-4" /><b>{data.novas} resposta(s) nova(s)</b>
      <span className="text-xs">{data.itens.slice(0, 3).map((i) => i.titular).join(", ")}{data.novas > 3 ? "…" : ""}. Continue a conversa pelo WhatsApp Business no celular; o sistema não responde.</span>
      <Button size="sm" variant="outline" className="ml-auto" onClick={() => api("/api/primeiro-contato-respostas/vistas", { method: "POST" }).then(() => reload())}>Marcar como vistas</Button>
    </div>
  );
}
