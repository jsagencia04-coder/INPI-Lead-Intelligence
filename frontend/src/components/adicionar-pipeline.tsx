"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, Info, Loader2, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { fmtDay } from "@/lib/format";
import { ETAPAS } from "@/lib/pipeline";
import { PROCURADOR, PRIORIDADE } from "@/lib/comercial";
import { cn } from "@/lib/utils";

/** V2.6 · Gestão comercial: encaminha UM processo do INPI ao Pipeline, sem duplicar o lead. */
type Ficha = {
  processo: {
    numero_processo: string; marca_nome: string | null; titular: string; geo_uf: string | null; geo_municipio: string | null; cnpj: string | null;
    lead_id: number | null; servico: string | null; tipo_decisao: string | null; despacho_codigo: string | null; despacho_nome: string | null;
    rpi_numero: number | null; data_publicacao: string | null; prazo_fim: string | null; procurador_situacao: string; procurador_nome: string | null;
    prioridade: number | null;
  };
  lead: { id: number; pipeline_stage: string; contatos: number; contatos_validados: number; whatsapp: string | null; consentimento: string | null; opt_out: boolean } | null;
  ja_no_pipeline: boolean;
  vinculo: { adicionado_em: string; adicionado_por: string; etapa_inicial: string } | null;
  outros_processos_do_titular: { numero_processo: string; marca_nome: string | null; no_pipeline: boolean }[];
  etapas_iniciais: { id: string; nome: string; bloqueada?: boolean }[];
  aviso: string | null;
};
type Resultado = { ja_existia: boolean; lead_id: number; etapa: string; mensagem: string };

const NOME_ETAPA = Object.fromEntries(ETAPAS.map((e) => [e.id, e.nome]));
const CONSENT: Record<string, string> = { ativo: "Autorização ativa", revogado: "Autorização revogada", pendente: "Aguardando autorização" };

export function linkPipeline(leadId: number, etapa: string) {
  return `/pipeline?etapa=${etapa}&lead=${leadId}`;
}

function Linha({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex justify-between gap-3 border-b py-1.5 text-sm last:border-0"><span className="text-muted-foreground">{k}</span><span className="text-right font-medium">{v}</span></div>;
}

export function AdicionarPipeline({ numero, onFechar, onFeito }: { numero: string; onFechar: () => void; onFeito?: () => void }) {
  const [f, setF] = useState<Ficha | null>(null);
  const [etapa, setEtapa] = useState("automatico");
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [res, setRes] = useState<Resultado | null>(null);

  useEffect(() => {
    api<Ficha>(`/api/pipeline/processo/${numero}`).then(setF).catch((e) => setErro(e instanceof Error ? e.message : String(e)));
  }, [numero]);

  const salvar = async () => {
    setOcupado(true); setErro(null);
    try {
      const r = await api<Resultado>(`/api/pipeline/processo/${numero}`, { method: "POST", body: JSON.stringify({ etapa }) });
      setRes(r); onFeito?.();
    } catch (e) { setErro(e instanceof Error ? e.message : String(e)); } finally { setOcupado(false); }
  };

  const p = f?.processo;
  const leadId = res?.lead_id ?? f?.lead?.id ?? p?.lead_id;
  const etapaAtual = res?.etapa ?? f?.lead?.pipeline_stage ?? "lead_novo";
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-label="Adicionar ao Pipeline" onClick={onFechar}>
      <div className="surface max-h-[90vh] w-full max-w-lg overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-lg font-semibold">Gestão comercial</h2>
          <button onClick={onFechar} className="ml-auto rounded-lg p-1.5 hover:bg-accent" aria-label="Fechar"><X className="size-4" /></button>
        </div>
        {erro && <div className="mb-3 rounded-md border border-destructive/40 bg-destructive/5 p-2 text-sm text-destructive">{erro}</div>}
        {!f ? (!erro && <div className="h-48 animate-pulse rounded-xl bg-muted" />) : (
          <>
            <Linha k="Titular" v={p!.titular} />
            <Linha k="Marca" v={p!.marca_nome ?? "—"} />
            <Linha k="Processo" v={<span className="font-mono">{p!.numero_processo}</span>} />
            <Linha k="Estado" v={p!.geo_uf ? `${p!.geo_municipio ? `${p!.geo_municipio} · ` : ""}${p!.geo_uf}` : "Sem UF identificada"} />
            <Linha k="Despacho" v={p!.prioridade ? <span className={cn("rounded-full px-2 py-0.5 text-xs", PRIORIDADE[p!.prioridade].classe)}>{PRIORIDADE[p!.prioridade].rotulo}</span> : (p!.despacho_nome ?? "—")} />
            <Linha k="Edição da RPI" v={p!.rpi_numero ? `nº ${p!.rpi_numero}${p!.data_publicacao ? ` · ${fmtDay(p!.data_publicacao)}` : ""}` : "—"} />
            <Linha k="Procurador" v={<span title={p!.procurador_nome ?? ""}>{PROCURADOR[p!.procurador_situacao]?.rotulo ?? p!.procurador_situacao}</span>} />
            <Linha k="Contato disponível" v={f.lead ? `${f.lead.contatos_validados} validado(s) de ${f.lead.contatos}` : "—"} />
            <Linha k="Consentimento" v={f.lead?.opt_out ? "Opt-out (bloqueado)" : (CONSENT[f.lead?.consentimento ?? ""] ?? "Sem autorização registrada")} />
            <Linha k="Etapa comercial" v={NOME_ETAPA[etapaAtual] ?? etapaAtual} />
            {f.aviso && <p className="mt-2 flex gap-1.5 rounded-md bg-amber-500/10 p-2 text-xs text-amber-900"><Info className="mt-0.5 size-3.5 shrink-0" />{f.aviso}</p>}

            {res || f.ja_no_pipeline ? (
              <div className={cn("mt-4 rounded-lg p-3 text-sm", res && !res.ja_existia ? "bg-emerald-500/10 text-emerald-900" : "bg-sky-500/10 text-sky-900")}>
                <div className="flex items-center gap-1.5 font-medium"><CheckCircle2 className="size-4" />{res ? res.mensagem : "Este processo já está cadastrado no Pipeline."}</div>
                {!res && f.vinculo && <div className="mt-1 text-xs">Adicionado em {fmtDay(f.vinculo.adicionado_em)} por {f.vinculo.adicionado_por.replace("user:", "")}.</div>}
                {leadId && <Link href={linkPipeline(leadId, etapaAtual)} className="mt-2 inline-flex items-center gap-1 font-medium text-primary hover:underline">
                  {res && !res.ja_existia ? "Abrir no Pipeline" : "Visualizar lead existente"}<ExternalLink className="size-3.5" /></Link>}
              </div>
            ) : (
              <div className="mt-4 space-y-2">
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">Etapa inicial
                  <select value={etapa} onChange={(e) => setEtapa(e.target.value)} className="h-9 rounded-lg border bg-card px-2 text-sm text-foreground">
                    {f.etapas_iniciais.map((e) => <option key={e.id} value={e.id} disabled={e.bloqueada}>{e.nome}{e.bloqueada ? " (exige resposta ou contato registrado)" : ""}</option>)}
                  </select>
                </label>
                <p className="text-[11px] text-muted-foreground">O lead não é duplicado: notas, histórico e responsáveis continuam os mesmos. Adicionar ao pipeline não autoriza contato pelo WhatsApp.</p>
                <Button onClick={salvar} disabled={ocupado || !p!.lead_id} className="w-full">
                  {ocupado ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}Adicionar ao Pipeline</Button>
                {!p!.lead_id && <p className="text-xs text-amber-700">O titular ainda não virou lead. Aguarde a montagem dos leads.</p>}
              </div>
            )}
            {f.outros_processos_do_titular.length > 0 && (
              <div className="mt-4">
                <div className="mb-1 text-xs font-semibold">Outras oportunidades do mesmo titular</div>
                <ul className="space-y-0.5 text-xs">{f.outros_processos_do_titular.map((o) => (
                  <li key={o.numero_processo} className="flex justify-between gap-2"><span className="font-mono">{o.numero_processo}</span><span className="truncate text-muted-foreground">{o.marca_nome ?? "—"}</span><span>{o.no_pipeline ? "no pipeline" : ""}</span></li>
                ))}</ul>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
