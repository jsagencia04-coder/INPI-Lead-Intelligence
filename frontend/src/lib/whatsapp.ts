/** WhatsApp: formatação e mensagem do primeiro contato (funções puras, testadas). */
import { fmtDay } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
export function formatWhats(e164: string) {
  const d = e164.replace(/\D/g, "");
  const m = d.match(/^55(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : e164;
}

/** Mensagem do primeiro contato, montada só com fatos do processo (nada inventado). */
export function mensagemInicial(lead: any, assinatura: string): string {
  const cat = lead.categoria_principal;
  const p = lead.processos.find((x: any) => x.ultimo_despacho) ?? lead.processos[0];
  const marca = p?.marca_nome ? `"${p.marca_nome}"` : "da sua empresa";
  const proc = p?.numero_processo ?? "";
  const rpi = p?.ultimo_despacho?.rpi ? `RPI nº ${p.ultimo_despacho.rpi}` : "Revista da Propriedade Industrial";
  const data = p?.ultimo_despacho?.data_publicacao ? ` (${fmtDay(p.ultimo_despacho.data_publicacao)})` : "";
  const quem = assinatura.trim() || "[seu nome]";
  const abertura = `Olá, tudo bem? Aqui é ${quem}, agente de propriedade industrial.`;
  const corpo: Record<string, string> = {
    oposicao: `Vi na ${rpi}${data} que o pedido de registro da marca ${marca} (processo ${proc}) foi publicado para oposição. Nessa fase vale acompanhar o prazo de oposição de terceiros.`,
    exigencia: `Vi na ${rpi}${data} uma exigência do INPI no processo ${proc}, da marca ${marca}. O prazo para cumprir é de 60 dias a partir da publicação.`,
    indeferimento: `Vi na ${rpi}${data} que o pedido da marca ${marca} (processo ${proc}) foi indeferido. Ainda é possível recorrer em até 60 dias a partir da publicação.`,
    extincao_prorrogacao: `Vi na ${rpi}${data} que o registro da marca ${marca} (processo ${proc}) foi extinto por fim da vigência, sem prorrogação. A marca ficou sem proteção.`,
  };
  return [abertura, corpo[cat] ?? `Acompanho publicações do INPI e vi o processo ${proc} da marca ${marca}.`,
    "Posso te explicar como funciona, sem compromisso?",
    "Se preferir não receber mensagens, é só responder SAIR."].join("\n\n");
}

