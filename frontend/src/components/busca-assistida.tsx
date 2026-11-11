"use client";

import { ExternalLink } from "lucide-react";

/* eslint-disable @typescript-eslint/no-explicit-any */

/** Buscas prontas no Google (gratuitas) para a pessoa encontrar o contato e cadastrá-lo com a fonte. */
export function BuscaAssistida({ titular, processos, cnpj, fantasia }: {
  titular: any; processos: any[]; cnpj?: string | null; fantasia?: string | null;
}) {
  const marcas = [...new Set(processos.map((p) => p.marca_nome).filter(Boolean))] as string[];
  const nome = titular.nome_original.replace(/\s+-?\s*(ME|EPP|EIRELI)$/i, "").trim();
  const uf = titular.uf ?? "";
  const cnpjFmt = cnpj ? cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5") : null;
  const buscas: [string, string][] = [
    [`"${nome}" contato`, "Titular + contato"],
    ...(fantasia ? [[`"${fantasia}" ${uf} contato`, "Nome fantasia + contato"] as [string, string]] : []),
    ...marcas.slice(0, 3).map((m) => [`"${m}" ${uf} site OR contato OR whatsapp`, `Marca ${m}`] as [string, string]),
    ...marcas.slice(0, 2).map((m) => [`site:instagram.com "${m}"`, `Instagram da marca ${m}`] as [string, string]),
    [`site:linkedin.com/company "${nome}"`, "LinkedIn da empresa"],
    ...(cnpjFmt ? [[`"${cnpjFmt}"`, "CNPJ em páginas da empresa"] as [string, string]] : []),
  ];
  return (
    <div className="rounded-md border border-dashed p-3">
      <div className="mb-2 text-sm font-medium">Busca assistida (gratuita)</div>
      <p className="mb-2 text-xs text-muted-foreground">
        Abra uma busca, confirme que a página é mesmo do titular (cidade, ramo e marca batem) e inclua o contato abaixo,
        colando a URL da página como fonte.
      </p>
      <div className="flex flex-wrap gap-2">
        {buscas.map(([q, rotulo]) => (
          <a key={q} href={`https://www.google.com/search?q=${encodeURIComponent(q)}`} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-accent" title={q}>
            {rotulo} <ExternalLink className="size-3" />
          </a>
        ))}
      </div>
    </div>
  );
}
