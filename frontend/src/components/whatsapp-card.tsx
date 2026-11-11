"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, MessageCircle, Search, ShieldCheck, X } from "lucide-react";
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
    </div>
  );
}
