"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AMBIENTE, authConfig, entrar, type AuthConfig } from "@/lib/auth";
import { supabase } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [cfg, setCfg] = useState<AuthConfig | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => { authConfig().then(setCfg).catch(() => setError("A API não está respondendo.")); }, []);

  if (cfg?.modo === "dev") {
    return <p className="text-sm text-muted-foreground">Ambiente de demonstração, sem login. Para exigir login, defina AUTH_MODE=local no backend.</p>;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setEnviando(true); setError(null);
    try {
      if (cfg?.modo === "supabase") {
        if (!supabase) throw new Error("Supabase não configurado nesta tela");
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw new Error(error.message);
      } else {
        await entrar(email, password);
      }
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally { setEnviando(false); }
  }

  return (
    <div className="flex min-h-[80vh] items-center justify-center">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>INPI Lead Intelligence</CardTitle>
          <CardDescription>Entre com sua conta{cfg ? ` · ${AMBIENTE[cfg.ambiente]}` : ""}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-3">
            <Input type="email" placeholder="E-mail" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
            <Input type="password" placeholder="Senha" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={enviando || !cfg}>{enviando ? "Entrando…" : "Entrar"}</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
