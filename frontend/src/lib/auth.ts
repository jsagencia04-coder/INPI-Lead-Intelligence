/** Sessão: login próprio (token no navegador) ou Supabase. As credenciais de serviços ficam só no backend. */
import { supabase } from "@/lib/supabase";

const API_URL = process.env.NEXT_PUBLIC_API_BASE ?? "";
const CHAVE = "inpi.token";

export type AuthConfig = { modo: "dev" | "local" | "supabase"; ambiente: "demo" | "homologacao" | "producao" };
export type Eu = { email: string | null; papel: "leitor" | "operador" | "revisor" | "admin"; modo: string; ambiente: string };

let cfg: Promise<AuthConfig> | null = null;
export function authConfig(): Promise<AuthConfig> {
  cfg ??= fetch(`${API_URL}/api/auth/config`, { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json() as Promise<AuthConfig>; })
    .catch((e) => { cfg = null; throw e; });
  return cfg;
}

export function tokenLocal(): string | null {
  try { return window.localStorage.getItem(CHAVE); } catch { return null; }
}
export function guardarToken(t: string | null) {
  try { if (t) window.localStorage.setItem(CHAVE, t); else window.localStorage.removeItem(CHAVE); } catch { /* navegador sem armazenamento */ }
}

/** Token da sessão atual, de qualquer um dos dois modos. */
export async function token(): Promise<string | null> {
  if (supabase) {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  }
  return typeof window === "undefined" ? null : tokenLocal();
}

export async function entrar(email: string, senha: string): Promise<void> {
  const r = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, senha }),
  });
  const corpo = await r.json().catch(() => null);
  if (!r.ok) throw new Error(corpo?.detail ?? "Não foi possível entrar");
  guardarToken(corpo.token);
}

export async function sair() {
  if (supabase) await supabase.auth.signOut();
  guardarToken(null);
  window.location.href = "/login";
}

export const PAPEL: Record<string, string> = { leitor: "Leitor", operador: "Operador", revisor: "Revisor", admin: "Administrador" };
export const AMBIENTE: Record<string, string> = { demo: "Demonstração", homologacao: "Homologação", producao: "Produção" };
