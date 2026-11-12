"use client";
/** Pendências priorizadas (/api/alerts), compartilhadas entre menu, sino e painel. Uma única consulta por página. */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export type Pendencia = {
  chave: string;
  severidade: "critico" | "aviso" | "oportunidade" | "info";
  quantidade: number;
  titulo: string;
  href: string;
  descricao: string;
};

type Ouvinte = (p: Pendencia[] | null) => void;
let atual: Pendencia[] | null = null;
const ouvintes = new Set<Ouvinte>();
let timer: ReturnType<typeof setInterval> | null = null;

async function buscar() {
  try {
    atual = await api<Pendencia[]>("/api/alerts");
  } catch {
    /* sem sessão ou API fora: mantém o último valor */
  }
  ouvintes.forEach((o) => o(atual));
}

export function recarregarAlertas() {
  return buscar();
}

export function useAlertas(): Pendencia[] | null {
  const [v, setV] = useState<Pendencia[] | null>(atual);
  useEffect(() => {
    ouvintes.add(setV);
    if (!timer) {
      buscar();
      timer = setInterval(buscar, 30000);
    } else setV(atual);
    return () => {
      ouvintes.delete(setV);
      if (!ouvintes.size && timer) { clearInterval(timer); timer = null; }
    };
  }, []);
  return v;
}

export const SEVERIDADE: Record<Pendencia["severidade"], { rotulo: string; ponto: string; texto: string; fundo: string }> = {
  critico: { rotulo: "Crítico", ponto: "bg-[var(--critical)]", texto: "text-red-700 dark:text-red-300", fundo: "bg-red-500/10" },
  aviso: { rotulo: "Atenção", ponto: "bg-[var(--warning)]", texto: "text-amber-800 dark:text-amber-300", fundo: "bg-amber-500/10" },
  oportunidade: { rotulo: "Oportunidade", ponto: "bg-[var(--success)]", texto: "text-emerald-700 dark:text-emerald-300", fundo: "bg-emerald-500/10" },
  info: { rotulo: "Para fazer", ponto: "bg-sky-500", texto: "text-sky-700 dark:text-sky-300", fundo: "bg-sky-500/10" },
};
