import { guardarToken, token } from "@/lib/auth";

// Vazio = mesmo endereço das telas (o Next.js repassa /api para o backend; ver next.config.ts).
// Vazio = mesmo endereço das telas: o Next.js repassa /api para o backend (ver next.config.ts).
// Obs.: a variável antiga NEXT_PUBLIC_API_URL é ignorada de propósito (causava "Failed to fetch"
// quando o .env.local da versão 0.1 apontava direto para http://localhost:8000).
const API_URL = process.env.NEXT_PUBLIC_API_BASE ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** 401 = sessão ausente ou vencida: limpa o token e volta para o login. */
function sessaoExpirada(status: number) {
  if (status === 401 && typeof window !== "undefined" && window.location.pathname !== "/login") {
    guardarToken(null);
    window.location.href = "/login";
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const t = await token();
  if (t) headers.set("Authorization", `Bearer ${t}`);
  const res = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    sessaoExpirada(res.status);
    const body = await res.json().catch(() => null);
    if (!body && res.status >= 500) {
      // resposta sem JSON = o repasse do Next.js não alcançou o backend
      throw new ApiError(res.status, "a API (backend, porta 8000) não está respondendo. Veja a janela do uvicorn");
    }
    throw new ApiError(res.status, body?.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

async function authHeaders(): Promise<Headers> {
  const headers = new Headers();
  const t = await token();
  if (t) headers.set("Authorization", `Bearer ${t}`);
  return headers;
}

/** Envia arquivo (multipart). */
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${API_URL}${path}`, { method: "POST", body, headers: await authHeaders() });
  if (!res.ok) {
    sessaoExpirada(res.status);
    const b = await res.json().catch(() => ({}));
    throw new ApiError(res.status, b.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

/** Baixa um arquivo autenticado e dispara o download no navegador. */
export async function apiDownload(path: string, filename: string) {
  const res = await fetch(`${API_URL}${path}`, { headers: await authHeaders() });
  if (!res.ok) {
    sessaoExpirada(res.status);
    const b = await res.json().catch(() => null);
    throw new ApiError(res.status, b?.detail ?? res.statusText);
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
