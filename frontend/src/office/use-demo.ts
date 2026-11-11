"use client";

import { useEffect, useMemo, useState } from "react";
import { AGENTES, DEPARTAMENTOS } from "./config";
import { demoStatus, deptStatus } from "./demo";
import type { AgentStatus, DeptStatus } from "./types";

/** Fonte de DEMONSTRAÇÃO. Na Etapa 5 é trocada pela fonte real (WebSocket do backend). */
export function useDemoOffice(intervaloMs = 2500) {
  const [tick, setTick] = useState(0);
  const [pausado, setPausado] = useState(false);

  useEffect(() => {
    const vis = () => setPausado(document.hidden);
    document.addEventListener("visibilitychange", vis);
    return () => document.removeEventListener("visibilitychange", vis);
  }, []);
  useEffect(() => {
    if (pausado) return;
    const t = setInterval(() => setTick((n) => n + 1), intervaloMs);
    return () => clearInterval(t);
  }, [pausado, intervaloMs]);

  return useMemo(() => {
    const agora = Date.now();
    const statuses: Record<string, AgentStatus> = {};
    AGENTES.forEach((a, i) => { statuses[a.id] = demoStatus(a, i, tick, agora); });
    const depts: Record<string, DeptStatus> = {};
    DEPARTAMENTOS.forEach((d) => {
      depts[d.id] = deptStatus(AGENTES.filter((a) => a.departamento === d.id).map((a) => statuses[a.id]));
    });
    return { statuses, depts, pausado, tick };
  }, [tick, pausado]);
}
