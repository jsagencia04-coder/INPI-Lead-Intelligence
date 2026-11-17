"use client";

import { useEffect, useRef } from "react";

/** Fundo interativo discreto: rede de pontos (marcas, processos, titulares) que se conectam e reagem ao cursor.
 *  Leve (canvas, ~70 pontos), pausa com a aba oculta e respeita "reduzir movimento". */
export function FundoRede({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = ref.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    const reduzido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0, h = 0, raf = 0;
    const mouse = { x: -9999, y: -9999 };
    type P = { x: number; y: number; vx: number; vy: number; r: number; destaque: boolean };
    let pts: P[] = [];

    function medir() {
      const r = cv!.getBoundingClientRect();
      w = r.width; h = r.height;
      cv!.width = w * dpr; cv!.height = h * dpr;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.round(Math.min(80, Math.max(35, (w * h) / 14000)));
      pts = Array.from({ length: n }, () => ({
        x: Math.random() * w, y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.25, vy: (Math.random() - 0.5) * 0.25,
        r: Math.random() * 1.4 + 0.8, destaque: Math.random() < 0.12,
      }));
    }

    function quadro() {
      ctx!.clearRect(0, 0, w, h);
      const lim = 130;
      for (const p of pts) {
        if (!reduzido) {
          p.x += p.vx; p.y += p.vy;
          if (p.x < 0 || p.x > w) p.vx *= -1;
          if (p.y < 0 || p.y > h) p.vy *= -1;
          const dx = p.x - mouse.x, dy = p.y - mouse.y, d = Math.hypot(dx, dy);
          if (d < 140 && d > 0) { p.x += (dx / d) * 0.6; p.y += (dy / d) * 0.6; }
        }
      }
      for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
          const a = pts[i], b = pts[j], d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < lim) {
            ctx!.strokeStyle = `rgba(125, 211, 252, ${0.16 * (1 - d / lim)})`;
            ctx!.lineWidth = 1;
            ctx!.beginPath(); ctx!.moveTo(a.x, a.y); ctx!.lineTo(b.x, b.y); ctx!.stroke();
          }
        }
        const dm = Math.hypot(pts[i].x - mouse.x, pts[i].y - mouse.y);
        if (dm < 180) {
          ctx!.strokeStyle = `rgba(56, 189, 248, ${0.35 * (1 - dm / 180)})`;
          ctx!.beginPath(); ctx!.moveTo(pts[i].x, pts[i].y); ctx!.lineTo(mouse.x, mouse.y); ctx!.stroke();
        }
      }
      for (const p of pts) {
        ctx!.fillStyle = p.destaque ? "rgba(251, 191, 36, 0.9)" : "rgba(186, 230, 253, 0.75)";
        ctx!.beginPath(); ctx!.arc(p.x, p.y, p.destaque ? p.r + 0.8 : p.r, 0, Math.PI * 2); ctx!.fill();
      }
      if (!reduzido && !document.hidden) raf = requestAnimationFrame(quadro);
    }

    const mover = (e: PointerEvent) => { const r = cv.getBoundingClientRect(); mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; };
    const sair = () => { mouse.x = mouse.y = -9999; };
    const visivel = () => { cancelAnimationFrame(raf); if (!document.hidden) raf = requestAnimationFrame(quadro); };
    const redimensionar = () => { medir(); visivel(); };
    medir(); raf = requestAnimationFrame(quadro);
    window.addEventListener("resize", redimensionar);
    window.addEventListener("pointermove", mover);
    window.addEventListener("pointerleave", sair);
    document.addEventListener("visibilitychange", visivel);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", redimensionar);
      window.removeEventListener("pointermove", mover);
      window.removeEventListener("pointerleave", sair);
      document.removeEventListener("visibilitychange", visivel);
    };
  }, []);

  return <canvas ref={ref} aria-hidden className={className} />;
}
