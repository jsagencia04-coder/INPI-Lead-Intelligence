"use client";

import { useState } from "react";
import { Ban, CheckCircle2, Loader2, PlugZap, PowerOff, RotateCcw, ShieldCheck, XCircle } from "lucide-react";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { useApi } from "@/components/use-api";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type Integracao = {
  provedor: string; instancia: string; configurada: boolean; simulacao: boolean; envio_habilitado: boolean; modo: "real" | "simulacao";
  envio_bloqueado: boolean; numero_autorizado: string | null; numeros_teste: number; webhook: string; webhook_configurado: boolean;
  remetente_configurado: boolean; meta_cloud_api: string;
  conta: { numero: string | null; status_conexao: string; verificado_em: string | null; detalhes: { detalhe?: string } } | null;
  contadores: Record<string, number>;
};
type Teste = { status: string; detalhe?: string; numero?: string | null; numero_confere: boolean; numero_autorizado: string | null };

const n = (v: number | undefined) => Number(v ?? 0).toLocaleString("pt-BR");
const ESTADO: Record<string, string> = {
  conectado: "Conectado", desconectado: "Desconectado", conectando: "Conectando", nao_configurada: "Não configurada", erro_autenticacao: "Chave recusada",
  instancia_inexistente: "Instância não encontrada", sem_conexao: "Sem conexão com a Evolution", timeout: "Sem resposta", desconhecido: "Ainda não verificado",
};

function Linha({ rotulo, valor, ok }: { rotulo: string; valor: React.ReactNode; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{rotulo}</span>
      <span className={cn("text-right font-medium", ok === true && "text-emerald-700", ok === false && "text-rose-700")}>{valor}</span>
    </div>
  );
}

export default function IntegracaoWhatsappPage() {
  const { data: d, error, reload } = useApi<Integracao>("/api/integracao-whatsapp", 30000);
  const [teste, setTeste] = useState<Teste | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const post = async <T,>(p: string) => {
    setOcupado(true); setErro(null);
    try { const r = await api<T>(p, { method: "POST" }); await reload(); return r; } catch (e) { setErro(e instanceof Error ? e.message : String(e)); return null; } finally { setOcupado(false); }
  };

  return (
    <>
      <PageHeader title="Integração WhatsApp" description="Provedor do primeiro contato, conexão da instância exclusiva do INPI Agent e travas de segurança. Nenhuma credencial é exibida." />
      <ErrorBox error={error ?? erro} />
      {d && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <section className="surface p-5">
            <div className="mb-3 flex items-center gap-2"><PlugZap className="size-5 text-primary" /><h2 className="font-semibold">Conexão</h2>
              <span className={cn("ml-auto rounded-full px-2.5 py-1 text-xs font-semibold", d.envio_bloqueado ? "bg-rose-500/15 text-rose-700" : d.modo === "real" ? "bg-emerald-500/15 text-emerald-700" : "bg-slate-500/15 text-slate-700")}>
                {d.envio_bloqueado ? "Envios desativados" : d.modo === "real" ? "Envio real ligado" : "Simulação"}</span></div>
            <Linha rotulo="Provedor selecionado" valor={d.provedor === "evolution" ? "Evolution API" : d.provedor === "meta" ? "Meta Cloud API" : "Manual (Abrir no WhatsApp)"} />
            <Linha rotulo="Instância" valor={d.instancia} />
            <Linha rotulo="Credenciais no servidor" valor={d.configurada ? "Configuradas" : "Faltando"} ok={d.configurada} />
            <Linha rotulo="Número vinculado" valor={d.conta?.numero ?? "—"} />
            <Linha rotulo="Número autorizado (INPI Agent)" valor={d.numero_autorizado ?? "não definido"} ok={!!d.numero_autorizado} />
            <Linha rotulo="Estado da conexão" valor={ESTADO[d.conta?.status_conexao ?? "desconhecido"] ?? d.conta?.status_conexao} ok={d.conta?.status_conexao === "conectado"} />
            <Linha rotulo="Última verificação" valor={d.conta?.verificado_em ? fmtDate(d.conta.verificado_em) : "—"} />
            <Linha rotulo="Simulação (EVOLUTION_SIMULATION)" valor={d.simulacao ? "Ligada" : "Desligada"} />
            <Linha rotulo="Envio real (EVOLUTION_SEND_ENABLED)" valor={d.envio_habilitado ? "Ligado" : "Desligado"} />
            <Linha rotulo="Números do teste controlado" valor={d.numeros_teste ? `${d.numeros_teste} número(s)` : "nenhum (todos os autorizados)"} />
            <Linha rotulo="Webhook exclusivo" valor={d.webhook_configurado ? "Token definido" : "Token não definido"} ok={d.webhook_configurado} />
            <Linha rotulo="Remetente na mensagem" valor={d.remetente_configurado ? "Definido" : "Usa a lacuna [seu nome]"} />
            <Linha rotulo="Meta Cloud API" valor={d.meta_cloud_api === "desativada" ? "Desativada (um provedor por vez)" : "Ativa"} />
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="outline" disabled={ocupado} onClick={async () => setTeste(await post<Teste>("/api/integracao-whatsapp/testar"))}>
                {ocupado ? <Loader2 className="size-4 animate-spin" /> : <PlugZap className="size-4" />}Testar conexão</Button>
              {d.envio_bloqueado ? (
                <Button variant="outline" disabled={ocupado} onClick={() => confirm("Reativar os envios? (só administrador)") && post("/api/integracao-whatsapp/reativar-envios")}><RotateCcw className="size-4" />Reativar envios</Button>
              ) : (
                <Button variant="destructive" disabled={ocupado} onClick={() => confirm("Desativar TODOS os envios agora? Mensagens na fila serão canceladas.") && post("/api/integracao-whatsapp/desativar-envios")}><PowerOff className="size-4" />Desativar envios</Button>
              )}
            </div>
            {teste && (
              <div className={cn("mt-3 flex items-start gap-2 rounded-lg p-2 text-sm", teste.status === "conectado" && teste.numero_confere ? "bg-emerald-500/10 text-emerald-800" : "bg-amber-500/10 text-amber-800")}>
                {teste.status === "conectado" && teste.numero_confere ? <CheckCircle2 className="mt-0.5 size-4" /> : <XCircle className="mt-0.5 size-4" />}
                <span>{ESTADO[teste.status] ?? teste.status}{teste.numero ? ` · número ${teste.numero}` : ""}{teste.numero && !teste.numero_confere ? " (NÃO é o número autorizado)" : ""}{teste.detalhe ? ` · ${teste.detalhe}` : ""}. Nenhuma mensagem foi enviada.</span>
              </div>
            )}
            <p className="mt-3 text-[11px] text-muted-foreground">Webhook a cadastrar na instância (Evolution Manager): <code className="rounded bg-muted px-1">{d.webhook}</code></p>
          </section>
          <section className="surface p-5">
            <div className="mb-3 flex items-center gap-2"><ShieldCheck className="size-5 text-primary" /><h2 className="font-semibold">Movimento</h2></div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {([["Rascunhos em revisão", d.contadores.rascunhos], ["Aprovados aguardando envio", d.contadores.aprovados], ["Enviados (reais)", d.contadores.enviados],
                ["Simulados", d.contadores.simulados], ["Falhas", d.contadores.falhas], ["A conferir no celular", d.contadores.a_conferir],
                ["Responderam", d.contadores.respostas], ["Contatos bloqueados (opt-out)", d.contadores.bloqueados]] as const).map(([k, v]) => (
                <div key={k} className="rounded-xl border p-3"><div className="text-[11px] text-muted-foreground">{k}</div><div className="num text-2xl font-semibold">{n(v)}</div></div>
              ))}
            </div>
            <ul className="mt-4 space-y-1.5 text-xs text-muted-foreground">
              <li className="flex gap-1.5"><Ban className="mt-0.5 size-3.5 shrink-0" />Sem chatbot, resposta automática, follow-up ou envio em massa: um envio por titular, aprovado por uma pessoa.</li>
              <li className="flex gap-1.5"><Ban className="mt-0.5 size-3.5 shrink-0" />Só sai mensagem com autorização do destinatário registrada. Telefone público não é autorização.</li>
              <li className="flex gap-1.5"><Ban className="mt-0.5 size-3.5 shrink-0" />Resultado incerto (tempo esgotado) nunca é reenviado sozinho: fica “a conferir no celular”.</li>
            </ul>
          </section>
        </div>
      )}
    </>
  );
}
