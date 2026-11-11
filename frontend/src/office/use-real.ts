"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { token } from "@/lib/auth";
import { mergeEvents, realOffice, type OfficeEvent, type OfficeState } from "./real";

export type Conexao = "conectando" | "tempo-real" | "consulta" | "offline";

/**
 * Fonte REAL: WebSocket /ws/office (eventos do banco via LISTEN/NOTIFY).
 * Se o WebSocket cair, reconecta com espera crescente e, enquanto isso,
 * consulta /api/office/state e /api/office/events a cada 3 s.
 */
export function useRealOffice(ativo: boolean) {
  const [estado, setEstado] = useState<OfficeState | null>(null);
  const [eventos, setEventos] = useState<OfficeEvent[]>([]);
  const [conexao, setConexao] = useState<Conexao>("conectando");
  const [erro, setErro] = useState<string | null>(null);
  const ultimo = useRef(0);

  useEffect(() => {
    if (!ativo) return;
    let ws: WebSocket | null = null;
    let parado = false;
    let tentativas = 0;
    let poll: ReturnType<typeof setInterval> | null = null;
    let religar: ReturnType<typeof setTimeout> | null = null;
    let ping: ReturnType<typeof setInterval> | null = null;

    const aplicar = (st?: OfficeState, evs?: OfficeEvent[]) => {
      if (st) setEstado(st);
      if (evs?.length) {
        ultimo.current = Math.max(ultimo.current, evs[evs.length - 1].id);
        setEventos((a) => mergeEvents(a, evs));
      }
      setErro(null);
    };

    const consultar = async () => {
      try {
        const [st, evs] = await Promise.all([
          api<OfficeState>("/api/office/state"),
          api<OfficeEvent[]>(`/api/office/events?after=${ultimo.current}&limit=200`),
        ]);
        aplicar(st, evs);
      } catch (e) {
        setErro(e instanceof Error ? e.message : String(e));
        setConexao("offline");
      }
    };
    const iniciarConsulta = () => {
      if (poll) return;
      setConexao((c) => (c === "offline" ? c : "consulta"));
      consultar();
      poll = setInterval(consultar, 3000);
    };
    const pararConsulta = () => { if (poll) clearInterval(poll); poll = null; };

    const conectar = async () => {
      if (parado) return;
      const params = new URLSearchParams({ after: String(ultimo.current) });
      const t = await token();
      if (t) params.set("token", t);
      const base = process.env.NEXT_PUBLIC_WS_URL
        ?? `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/office`;
      ws = new WebSocket(`${base}?${params}`);
      ws.onopen = () => { tentativas = 0; };
      ws.onmessage = (m) => {
        const d = JSON.parse(m.data);
        aplicar(d.estado, d.eventos);
        setConexao("tempo-real");
        pararConsulta();
      };
      ws.onclose = () => {
        if (ping) clearInterval(ping);
        if (parado) return;
        iniciarConsulta();
        const espera = [1000, 2000, 5000, 10000, 30000][Math.min(tentativas++, 4)];
        religar = setTimeout(conectar, espera);
      };
      ping = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send("ping"), 25000);
    };

    // primeira carga imediata pela API, depois o WebSocket assume
    consultar().then(conectar);
    return () => {
      parado = true;
      ws?.close();
      pararConsulta();
      if (religar) clearTimeout(religar);
      if (ping) clearInterval(ping);
    };
  }, [ativo]);

  const derivado = useMemo(() => (estado ? realOffice(estado) : null), [estado]);
  return { estado, eventos, conexao, erro, ...(derivado ?? { statuses: null, depts: null }) };
}
