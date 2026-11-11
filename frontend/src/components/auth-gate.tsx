"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { authConfig, token } from "@/lib/auth";

/** Só mostra as telas com sessão válida. No modo dev (ambiente demo) não há login. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let vivo = true;
    if (pathname === "/login") { setReady(true); return; }
    (async () => {
      let modo = "dev";
      try { modo = (await authConfig()).modo; } catch { /* API fora do ar: as telas mostram o erro */ }
      if (!vivo) return;
      if (modo !== "dev" && !(await token())) router.replace("/login");
      else setReady(true);
    })();
    return () => { vivo = false; };
  }, [pathname, router]);

  return ready ? <>{children}</> : null;
}
