"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, ExternalLink, Loader2, MessageCircle, Search, Send, ShieldCheck, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { formatWhats, mensagemInicial } from "@/lib/whatsapp";

export { formatWhats };

/* eslint-disable @typescript-eslint/no-explicit-any */
const NIVEL: Record<string, { rotulo: string; classe: string; texto: string }> = {
  verificado_humano: { rotulo: "Confirmado por você", classe: "bg-emerald-600 text-white", texto: "Você confirmou que o número tem WhatsApp e é da empresa." },
  dominio_ok: { rotulo: "Validado pela empresa", classe: "bg-emerald-100 text-emerald-900", texto: "A própria empresa publica este número como WhatsApp na fonte abaixo." },
  formato_ok: { rotulo: "Candidato", classe: "bg-amber-100 text-amber-900", texto: "Celular encontrado, mas a fonte não diz que é WhatsApp. Confirme antes de usar." },
  encontrado: { rotulo: "Candidato", classe: "bg-amber-100 text-amber-900", texto: "Ainda não validado." },
};
const ORDEM = ["verificado_humano", "dominio_ok", "formato_ok", "encontrado"];

export function WhatsappCard({ lead, podeProspectar, onChange }: { lead: any; podeProspectar: boolean; onChange: () => void }) {
  const lista = lead.contatos.filter((c: any) => c.tipo === "whatsapp" && c.verificacao !== "invalido")
    .sort((a: any, b: any) => ORDEM.indexOf(a.verificacao) - ORDEM.indexOf(b.verificacao));
  const [idx, setIdx] = useState(0);
  const atual = lista[Math.min(idx, Math.max(lista.length - 1, 0))];
  const [assinatura, setAssinatura] = useState("");
  const [texto, setTexto] = useState("");
  const [aberto, setAberto] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  // V2.8 · envio direto pela Evolution (um clique): texto do modelo do banco, sem wa.me nem nova aba
  const [det, setDet] = useState<any>(null);
  const [textoEvo, setTextoEvo] = useState("");
  const [envio, setEnvio] = useState<any>(null);
  const [enviando, setEnviando] = useState(false);
  const [erroEvo, setErroEvo] = useState<string | null>(null);
  const chave = useRef<string | null>(null);
  const carregar = async () => {
    try {
      const d: any = await api(`/api/primeiro-contato/${lead.id}`);
      setDet(d);
      if (d.provedor !== "evolution") return;
      const r = d.rascunho && ["rascunho", "aprovado"].includes(d.rascunho.status) ? d.rascunho : null;
      if (r) setTextoEvo(r.conteudo);
      else {
        const p: any = await api(`/api/wa-modelos/${d.modelo_sugerido}/previa`, { method: "POST", body: JSON.stringify({ lead_id: lead.id }) });
        setTextoEvo(p.texto);
      }
      const ultimo = d.envios.find((e: any) => e.direcao === "saida" && e.modo === "real" && !["falhou", "bloqueada", "cancelada"].includes(e.status));
      if (ultimo) setEnvio(ultimo);
    } catch { setDet(null); }
  };
  useEffect(() => { carregar(); }, [lead.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {  // acompanha até a confirmação de entrega do WhatsApp
    if (!envio || !["aceita", "enviada", "na_fila"].includes(envio.status)) return;
    let n = 0;
    const t = setInterval(async () => {
      n += 1;
      try { const m: any = await api(`/api/wa-mensagens/${envio.id}`); if (m.status !== envio.status) setEnvio(m); } catch { /* mantém */ }
      if (n >= 60) clearInterval(t);
    }, 3000);
    return () => clearInterval(t);
  }, [envio]);

  useEffect(() => {
    try { setAssinatura(localStorage.getItem("inpi.assinatura") ?? ""); } catch { /* sem armazenamento */ }
  }, []);
  useEffect(() => { setTexto(mensagemInicial(lead, assinatura)); }, [lead, assinatura]);

  const salvarAssinatura = (v: string) => {
    setAssinatura(v);
    try { localStorage.setItem("inpi.assinatura", v); } catch { /* ignore */ }
  };
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); setMsg(ok); onChange(); } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  const registrar = (resultado: string, invalidar = false) => act(async () => {
    if (invalidar) await api(`/api/contacts/${atual.id}/verify`, { method: "POST", body: JSON.stringify({ verificacao: "invalido", observacao: "sem WhatsApp" }) });
    else await api(`/api/leads/${lead.id}/outreach`, { method: "POST", body: JSON.stringify({ canal: "whatsapp", contact_id: atual.id, resultado }) });
    setAberto(false);
  }, invalidar ? "Número marcado como sem WhatsApp." : "Contato registrado no histórico de prospecção.");

  const nome = lead.titular.nome_original;
  const marca = lead.processos.find((p: any) => p.marca_nome)?.marca_nome;
  const busca = `https://www.google.com/search?q=${encodeURIComponent(`"${marca ?? nome}" whatsapp`)}`;

  if (!atual) {
    return (
      <div className="rounded-xl border border-dashed p-4">
        <div className="flex items-center gap-2 font-semibold"><MessageCircle className="size-5 text-[#25D366]" /> WhatsApp comercial</div>
        <p className="mt-1 text-sm text-muted-foreground">
          Nenhum WhatsApp encontrado ainda. A busca automática procura links wa.me e números indicados como WhatsApp no site
          oficial. Você também pode procurar e cadastrar abaixo, em &quot;Dados comerciais&quot;, com o tipo WhatsApp e a fonte.
        </p>
        <a href={busca} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs hover:bg-accent">
          <Search className="size-3.5" /> Procurar o WhatsApp no Google <ExternalLink className="size-3" />
        </a>
      </div>
    );
  }

  const enviarAgora = async () => {
    setErroEvo(null); setEnviando(true);
    if (!chave.current) chave.current = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    try {
      const m: any = await api(`/api/primeiro-contato/${lead.id}/enviar`, { method: "POST", body: JSON.stringify({ contact_id: atual.id, texto: textoEvo, chave: chave.current }) });
      setEnvio(m);
      if (["falhou", "bloqueada"].includes(m.status)) { setErroEvo(m.motivo ?? "Falha no envio"); chave.current = null; }
      if (m.status === "reconciliar") setErroEvo("Sem resposta do WhatsApp a tempo: confira no celular se a mensagem saiu (nada é reenviado sozinho).");
      onChange();
    } catch (e) { setErroEvo(e instanceof Error ? e.message : String(e)); chave.current = null; } finally { setEnviando(false); }
  };
  const evo = det?.provedor === "evolution";
  const enviado = envio && ["aceita", "enviada", "entregue", "lida", "simulada"].includes(envio.status);
  const rotuloEnvio = !envio ? "" : envio.status === "simulada" ? "Simulado (nada saiu)" : ["entregue", "lida"].includes(envio.status) ? "Entregue" : envio.status === "reconciliar" ? "Conferir no celular" : "Enviada";
  const consentido = det?.consentimentos?.some((k: any) => k.contact_id === atual.id && k.status === "ativo");
  const lacuna = /\[[^\]]{2,40}\]/.test(textoEvo);

  const nivel = NIVEL[atual.verificacao] ?? NIVEL.encontrado;
  const digitos = atual.valor_normalizado.replace(/\D/g, "");
  const link = `https://wa.me/${digitos}?text=${encodeURIComponent(texto)}`;

  return (
    <div className="rounded-xl border-2 border-[#25D366]/40 bg-gradient-to-br from-[#25D366]/5 to-transparent p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold"><MessageCircle className="size-5 text-[#25D366]" /> WhatsApp comercial · primeiro contato</div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="text-2xl font-semibold tabular-nums tracking-tight">{formatWhats(atual.valor_normalizado)}</span>
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${nivel.classe}`}>{nivel.rotulo}</span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{nivel.texto}</p>
          {atual.fonte_url?.startsWith("http")
            ? <a href={atual.fonte_url} target="_blank" rel="noreferrer" className="break-all text-xs text-muted-foreground underline">Fonte: {atual.fonte_url}</a>
            : <span className="text-xs text-muted-foreground">Fonte: {atual.fonte_url}</span>}
          {lista.length > 1 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {lista.map((c: any, i: number) => (
                <button key={c.id} onClick={() => setIdx(i)} className={`rounded-md border px-2 py-0.5 text-xs ${i === idx ? "border-foreground" : ""}`}>
                  {formatWhats(c.valor_normalizado)}</button>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {atual.verificacao !== "verificado_humano" && (
            <Button size="sm" variant="outline" onClick={() => act(() => api(`/api/contacts/${atual.id}/verify`,
              { method: "POST", body: JSON.stringify({ verificacao: "verificado_humano", observacao: "WhatsApp confirmado" }) }), "WhatsApp confirmado.")}>
              <ShieldCheck className="size-4" /> Confirmar WhatsApp</Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => registrar("", true)}><X className="size-4" /> Não é WhatsApp</Button>
        </div>
      </div>

      {evo ? (
        <div className="mt-4 grid gap-2">
          <Textarea value={textoEvo} onChange={(e) => setTextoEvo(e.target.value)} rows={8} disabled={!!enviado || enviando}
            className="bg-background text-sm" aria-label="Mensagem do WhatsApp" />
          {lacuna && !enviado && <p className="flex items-center gap-1.5 text-xs text-amber-800"><AlertTriangle className="size-3.5" />Complete o texto entre colchetes (ex.: [marca]) antes de enviar.</p>}
          {!consentido && !enviado && <p className="flex items-center gap-1.5 text-xs text-amber-800"><AlertTriangle className="size-3.5" />Sem autorização do destinatário registrada: o envio será recusado. Registre a autorização na Central de contatos.</p>}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" onClick={enviarAgora} disabled={!podeProspectar || enviando || !!enviado || lacuna || !textoEvo.trim()}
              className={`min-w-36 text-white ${enviado ? "bg-emerald-700 hover:bg-emerald-700" : "bg-[#25D366] hover:bg-[#1ebe5a]"}`}>
              {enviando ? <Loader2 className="size-4 animate-spin" /> : enviado ? <CheckCircle2 className="size-4" /> : <Send className="size-4" />}
              {enviando ? "Enviando..." : enviado ? rotuloEnvio : "Enviar"}
            </Button>
            {!podeProspectar && <span className="text-xs text-muted-foreground">Aprove o lead para prospecção para enviar.</span>}
            {enviado && envio.status !== "simulada" && !["entregue", "lida"].includes(envio.status) && <span className="text-xs text-muted-foreground">Aguardando a confirmação de entrega…</span>}
            <Link href={`/primeiro-contato?lead=${lead.id}`} className="ml-auto text-xs text-muted-foreground underline">Requisitos e histórico do envio</Link>
          </div>
          {erroEvo && <p className="rounded-md bg-rose-500/10 p-2 text-xs text-rose-800">{erroEvo}</p>}
          {msg && <p className="text-xs">{msg}</p>}
          <p className="text-[11px] text-muted-foreground">
            O clique em Enviar aprova este texto e o envia na hora pelo número do INPI Agent, sem abrir outra página. Um primeiro contato por titular;
            as respostas chegam no WhatsApp Business do celular e o sistema não responde sozinho. {det?.modo !== "real" && "Modo simulação: nada sai do sistema."}
          </p>
        </div>
      ) : (
      <div className="mt-4 grid gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Assinar como</span>
          <Input value={assinatura} onChange={(e) => salvarAssinatura(e.target.value)} placeholder="Seu nome" className="h-8 w-56" />
        </div>
        <Textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={7} className="bg-background text-sm" aria-label="Mensagem do WhatsApp" />
        <div className="flex flex-wrap items-center gap-2">
          {podeProspectar ? (
            <a href={link} target="_blank" rel="noreferrer" onClick={() => setAberto(true)}
              className="inline-flex items-center gap-2 rounded-md bg-[#25D366] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#1ebe5a]">
              <MessageCircle className="size-4" /> Abrir conversa no WhatsApp
            </a>
          ) : (
            <span className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
              Aprove o lead (botão &quot;Aprovar para prospecção&quot;) para abrir a conversa com a mensagem.</span>
          )}
          <a href={`https://wa.me/${digitos}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-muted-foreground underline">
            Só verificar se o número tem WhatsApp <ExternalLink className="size-3" /></a>
          {texto.includes("[seu nome]") && <Badge variant="outline" className="border-amber-400 text-amber-800">preencha seu nome</Badge>}
        </div>
        {aberto && (
          <div className="flex flex-wrap items-center gap-2 rounded-md bg-muted p-2 text-xs">
            <CheckCircle2 className="size-4 text-emerald-600" /> Como foi?
            <Button size="sm" variant="outline" onClick={() => registrar("mensagem enviada pelo WhatsApp")}>Mensagem enviada</Button>
            <Button size="sm" variant="outline" onClick={() => registrar("respondeu no WhatsApp")}>Respondeu</Button>
            <Button size="sm" variant="outline" onClick={() => registrar("", true)}>Número sem WhatsApp</Button>
            <Button size="sm" variant="ghost" onClick={() => setAberto(false)}>Não enviei</Button>
          </div>
        )}
        {msg && <p className="text-xs">{msg}</p>}
        <p className="text-[11px] text-muted-foreground">
          O envio é sempre manual, um a um: o sistema não dispara mensagens. Os prazos citados são estimativas (60 dias da
          publicação); confira no INPI. Se a pessoa pedir para sair, use &quot;Opt-out do titular&quot;.
        </p>
      </div>
      )}
    </div>
  );
}
