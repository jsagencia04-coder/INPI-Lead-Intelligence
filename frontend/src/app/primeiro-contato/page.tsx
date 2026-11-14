"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { FileSignature, MessageCircle } from "lucide-react";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { AvisoRespostas, ENVIO, PrimeiroContatoPainel } from "@/components/primeiro-contato-painel";
import { Select } from "@/components/select";
import { Input } from "@/components/ui/input";
import { useApi } from "@/components/use-api";
import { fmtDay } from "@/lib/format";
import { CLASSE, SERVICO, TIPO_DECISAO, type Classe, type Servico } from "@/lib/servicos";
import { cn } from "@/lib/utils";

type Linha = {
  lead_id: number; titular: string; geo_uf: string | null; geo_municipio: string | null; classe_principal: Classe | null;
  servico: Servico | null; tipo_decisao: keyof typeof TIPO_DECISAO | null; numero_processo: string | null; marca_nome: string | null;
  data_publicacao: string | null; prazo_fim: string | null; contact_id: number; whatsapp: string; wa_nivel: string | null;
  origem_tipo: string | null; origem_url: string | null; consentimento: string | null;
  rascunho: { id: number; status: string; versao: number; aprovado_por: string | null } | null; contato_status: string | null;
};
const RASCUNHO: Record<string, { rotulo: string; classe: string }> = {
  rascunho: { rotulo: "Em revisão", classe: "bg-amber-500/15 text-amber-800" },
  aprovado: { rotulo: "Aprovado", classe: "bg-emerald-500/15 text-emerald-700" },
  rejeitado: { rotulo: "Rejeitado", classe: "bg-zinc-500/15 text-zinc-600" },
  enviado: { rotulo: "Enviado", classe: "bg-sky-500/15 text-sky-700" },
};
const CONSENT: Record<string, string> = { ativo: "Autorizado", revogado: "Revogado", expirado: "Expirado" };

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
      <PageHeader title="Primeiro contato" description="Uma única mensagem por titular, preparada a partir de um dos três modelos, aprovada por uma pessoa e enviada pelo sistema só com autorização do destinatário. Depois, a conversa é sua no WhatsApp Business.">
        <Link href="/configuracoes-mensagens" className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium hover:bg-accent">Configurações de mensagens</Link>
        <Link href="/integracao-whatsapp" className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium",
          integ?.envio_bloqueado ? "bg-rose-500/15 text-rose-700" : integ?.modo === "real" ? "bg-emerald-500/15 text-emerald-700" : "bg-slate-500/15 text-slate-700")}>
          <MessageCircle className="size-3.5" />{integ ? (integ.envio_bloqueado ? "Envios desativados" : integ.modo === "real" ? `Envio real · ${integ.provedor}` : `Simulação · ${integ.provedor}`) : "…"}
        </Link>
      </PageHeader>
      <ErrorBox error={error} />
      <AvisoRespostas />
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
          {sel ? <PrimeiroContatoPainel key={sel} leadId={sel} onMudou={reload} /> : <p className="py-16 text-center text-sm text-muted-foreground">Escolha um lead na lista para preparar a mensagem.</p>}
        </section>
      </div>
    </>
  );
}

export default function PrimeiroContatoPage() {
  return <Suspense><Pagina /></Suspense>;
}
