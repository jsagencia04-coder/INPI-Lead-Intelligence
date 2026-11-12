"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Mail, ShieldCheck, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/select";
import { api } from "@/lib/api";
import type { ContatoCentral } from "@/lib/contatos";
import { fmtDay } from "@/lib/format";

type Regra = { regra: string; ok: boolean; detalhe: string };
type Consent = { id: number; canal: string; status: string; metodo: string; obtido_em: string; fonte_evidencia: string; texto_autorizacao: string; numero_fornecido: boolean; revogado_em: string | null; revogacao_origem: string | null };
type Pedido = { id: number; status: string; criado_em: string; texto: string };
type Dados = { consentimentos: Consent[]; pedidos: Pedido[] };

const METODOS = { email: "Resposta por e-mail", resposta_whatsapp: "Mensagem que o titular enviou no WhatsApp", telefone: "Ligação telefônica", formulario: "Formulário", presencial: "Presencialmente", contrato: "Contrato", outro: "Outro" };
const ASSINATURA = "inpi.assinatura";

/** Autorização para WhatsApp de um contato: regras de elegibilidade, pedido por e-mail e registro da prova. */
export function Consentimento({ contato, emails }: { contato: ContatoCentral; emails: ContatoCentral[] }) {
  const [regras, setRegras] = useState<Regra[] | null>(null);
  const [dados, setDados] = useState<Dados | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [quem, setQuem] = useState("");
  const [via, setVia] = useState(emails[0] ? String(emails[0].id) : "");
  const [form, setForm] = useState({ metodo: "email", obtido_em: new Date().toISOString().slice(0, 10), fonte_evidencia: "", texto_autorizacao: "", numero_fornecido: false });

  const carregar = useCallback(async () => {
    try {
      const [e, d] = await Promise.all([
        api<{ regras: Regra[] }>(`/api/contacts/${contato.id}/elegibilidade`),
        api<Dados>(`/api/contacts/${contato.id}/consents`),
      ]);
      setRegras(e.regras); setDados(d);
    } catch (err) { setMsg(err instanceof Error ? err.message : String(err)); }
  }, [contato.id]);
  useEffect(() => { carregar(); try { setQuem(window.localStorage.getItem(ASSINATURA) ?? ""); } catch { /* sem armazenamento */ } }, [carregar]);

  const acao = async (fn: () => Promise<unknown>, ok: string) => {
    setMsg(null);
    try { await fn(); setMsg(ok); await carregar(); } catch (err) { setMsg(err instanceof Error ? err.message : String(err)); }
  };
  const guardarQuem = (v: string) => { setQuem(v); try { window.localStorage.setItem(ASSINATURA, v); } catch { /* sem armazenamento */ } };

  const pedir = () => acao(async () => {
    const p = await api<{ mailto: string }>(`/api/contacts/${contato.id}/consent-requests`, { method: "POST", body: JSON.stringify({ via_contact_id: Number(via), empresa_identificada: quem }) });
    window.location.href = p.mailto; // abre o seu programa de e-mail com o texto pronto; quem envia é você
  }, "Pedido registrado. O seu programa de e-mail foi aberto com o texto: confira e envie.");

  const registrar = () => acao(() => api(`/api/contacts/${contato.id}/consents`, {
    method: "POST",
    body: JSON.stringify({ ...form, obtido_em: new Date(form.obtido_em + "T12:00:00").toISOString(), empresa_identificada: quem, pedido_id: dados?.pedidos.find((p) => p.status === "enviado")?.id ?? null }),
  }), "Autorização registrada.");

  const ativo = dados?.consentimentos.find((k) => k.status === "ativo" && k.canal === "whatsapp");
  const aberto = dados?.pedidos.find((p) => p.status === "enviado");

  return (
    <div className="mt-2 space-y-3 rounded-md border bg-background p-3 text-xs">
      <div>
        <div className="mb-1 font-medium">Pode receber WhatsApp?</div>
        {!regras ? "Conferindo…" : (
          <ul className="space-y-0.5">
            {regras.map((r) => (
              <li key={r.regra} className="flex items-start gap-1.5">
                {r.ok ? <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-emerald-600" /> : <XCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />}
                <span>{r.detalhe}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {dados && dados.consentimentos.length > 0 && (
        <div>
          <div className="mb-1 font-medium">Autorizações</div>
          {dados.consentimentos.map((k) => (
            <div key={k.id} className="flex flex-wrap items-center gap-2 border-t py-1">
              <ShieldCheck className={`size-3.5 ${k.status === "ativo" ? "text-emerald-600" : "text-muted-foreground"}`} />
              <span>{k.status === "ativo" ? "Ativa" : "Revogada"} · {fmtDay(k.obtido_em)} · {METODOS[k.metodo as keyof typeof METODOS] ?? k.metodo}</span>
              <span className="text-muted-foreground">prova: {k.fonte_evidencia}{k.revogado_em ? ` · revogada em ${fmtDay(k.revogado_em)} (${k.revogacao_origem})` : ""}</span>
              {k.status === "ativo" && (
                <Button size="sm" variant="outline" className="ml-auto h-6 text-xs" onClick={() => {
                  const origem = window.prompt("Motivo da revogação (ex.: pediu por telefone):");
                  if (origem) acao(() => api(`/api/consents/${k.id}/revoke`, { method: "POST", body: JSON.stringify({ origem }) }), "Autorização revogada.");
                }}>Revogar</Button>
              )}
            </div>
          ))}
        </div>
      )}

      {!ativo && (
        <>
          <div>
            <label className="mb-1 block font-medium">Como você se apresenta</label>
            <Input value={quem} onChange={(e) => guardarQuem(e.target.value)} placeholder="Ex.: Fulano de Tal, agente de propriedade industrial" className="h-8 max-w-md text-xs" />
          </div>
          <div>
            <div className="mb-1 font-medium">1. Pedir autorização por e-mail</div>
            {aberto ? <p className="text-muted-foreground">Pedido enviado em {fmtDay(aberto.criado_em)}. Aguardando resposta.</p>
              : emails.length === 0 ? <p className="text-muted-foreground">Este titular não tem e-mail cadastrado para fazer o pedido.</p>
              : (
                <div className="flex flex-wrap items-center gap-2">
                  <Select value={via} onChange={setVia} options={Object.fromEntries(emails.map((e) => [String(e.id), e.valor_normalizado]))} className="h-8 text-xs" />
                  <Button size="sm" variant="outline" className="h-8 text-xs" disabled={!quem.trim() || !via} onClick={pedir}><Mail className="size-3.5" /> Preparar e-mail</Button>
                  <span className="text-muted-foreground">O sistema não envia: abre o seu e-mail com o texto pronto.</span>
                </div>
              )}
          </div>
          <div>
            <div className="mb-1 font-medium">2. Registrar a autorização recebida</div>
            <div className="grid max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
              <Select value={form.metodo} onChange={(v) => setForm({ ...form, metodo: v })} options={METODOS} className="h-8 text-xs" />
              <Input type="date" value={form.obtido_em} onChange={(e) => setForm({ ...form, obtido_em: e.target.value })} className="h-8 text-xs" />
              <Input value={form.fonte_evidencia} onChange={(e) => setForm({ ...form, fonte_evidencia: e.target.value })} placeholder="Onde está a prova (ex.: e-mail de 10/11, assunto…)" className="h-8 text-xs sm:col-span-2" />
              <Textarea value={form.texto_autorizacao} onChange={(e) => setForm({ ...form, texto_autorizacao: e.target.value })} placeholder="Texto exato da autorização dada pelo titular" className="min-h-14 text-xs sm:col-span-2" />
              <label className="flex items-center gap-2 sm:col-span-2">
                <input type="checkbox" checked={form.numero_fornecido} onChange={(e) => setForm({ ...form, numero_fornecido: e.target.checked })} />
                O próprio titular informou este número de WhatsApp
              </label>
            </div>
            <Button size="sm" className="mt-2 h-8 text-xs" disabled={!quem.trim() || form.fonte_evidencia.trim().length < 3 || form.texto_autorizacao.trim().length < 2} onClick={registrar}>Registrar autorização</Button>
            <p className="mt-1 text-muted-foreground">Registre só autorização que você realmente recebeu. Fica gravado quem registrou e quando.</p>
          </div>
        </>
      )}
      {msg && <div className="rounded border bg-muted/40 p-2">{msg}</div>}
    </div>
  );
}
