"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Eye, EyeOff, Loader2, Lock, Mail, MapPinned, ShieldCheck, Zap } from "lucide-react";
import { FundoRede } from "@/components/fundo-rede";
import { LogoAgente, NOME_SISTEMA } from "@/components/marca";
import { AMBIENTE, authConfig, entrar, type AuthConfig } from "@/lib/auth";
import { supabase } from "@/lib/supabase";

const DESTAQUES = [
  { icone: Zap, titulo: "Revista do INPI em tempo real", texto: "Cada edição lida assim que é publicada, PDF e XML em paralelo." },
  { icone: MapPinned, titulo: "Oportunidades por estado", texto: "Oposições e indeferimentos priorizados, começando por Santa Catarina." },
  { icone: ShieldCheck, titulo: "Contato com segurança", texto: "Consentimento, descadastro e trilha de auditoria em cada envio." },
];

export default function LoginPage() {
  const router = useRouter();
  const [cfg, setCfg] = useState<AuthConfig | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [ver, setVer] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => { authConfig().then(setCfg).catch(() => setError("O servidor não está respondendo. Tente novamente em instantes.")); }, []);

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

  const ano = new Date().getFullYear();
  const naoProducao = cfg && cfg.ambiente !== "producao";

  return (
    <div className="fixed inset-0 z-50 flex overflow-auto bg-[#071427] text-slate-100 lg:bg-white lg:text-slate-900">
      {/* Painel institucional com fundo interativo */}
      <section className="relative hidden flex-1 overflow-hidden bg-[radial-gradient(120%_90%_at_10%_0%,#123a6b_0%,#0b1f3a_45%,#061224_100%)] lg:flex lg:flex-col">
        <FundoRede className="absolute inset-0 h-full w-full" />
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,transparent_60%,rgba(6,18,36,0.55))]" />
        <div className="relative z-10 flex flex-1 flex-col justify-between p-12 xl:p-16">
          <div className="flex items-center gap-3">
            <LogoAgente className="size-11 drop-shadow-lg" />
            <div className="leading-tight">
              <div className="text-lg font-semibold tracking-tight text-white">{NOME_SISTEMA}</div>
              <div className="text-xs uppercase tracking-[0.18em] text-sky-300/80">Inteligência em propriedade industrial</div>
            </div>
          </div>

          <div className="max-w-xl">
            <h1 className="text-4xl font-semibold leading-[1.15] tracking-tight text-white xl:text-5xl">
              Cada publicação do INPI,<br />
              <span className="bg-gradient-to-r from-sky-300 to-blue-400 bg-clip-text text-transparent">uma oportunidade de negócio.</span>
            </h1>
            <p className="mt-5 max-w-lg text-base leading-relaxed text-slate-300">
              Monitoramento da Revista da Propriedade Industrial, qualificação de titulares e gestão comercial em uma única plataforma.
            </p>
            <ul className="mt-10 space-y-5">
              {DESTAQUES.map(({ icone: Icone, titulo, texto }) => (
                <li key={titulo} className="flex gap-4">
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-sky-400/20 bg-sky-400/10 text-sky-300 backdrop-blur">
                    <Icone className="size-5" />
                  </span>
                  <span>
                    <span className="block text-sm font-semibold text-white">{titulo}</span>
                    <span className="block text-sm text-slate-400">{texto}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <p className="text-xs text-slate-500">© {ano} {NOME_SISTEMA}. Acesso restrito a usuários autorizados.</p>
        </div>
      </section>

      {/* Formulário */}
      <section className="relative flex w-full flex-col items-center justify-center px-6 py-10 lg:w-[480px] lg:shrink-0 xl:w-[540px]">
        <FundoRede className="absolute inset-0 h-full w-full opacity-60 lg:hidden" />
        <div className="relative z-10 w-full max-w-sm">
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <LogoAgente className="size-10" />
            <div className="text-lg font-semibold text-white">{NOME_SISTEMA}</div>
          </div>

          <div className="rounded-2xl bg-white p-8 text-slate-900 shadow-2xl shadow-black/30 lg:rounded-none lg:p-0 lg:shadow-none">
            <h2 className="text-2xl font-semibold tracking-tight">Bem-vindo de volta</h2>
            <p className="mt-1.5 text-sm text-slate-500">
              Entre com suas credenciais para acessar a plataforma.
              {naoProducao && <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-800">{AMBIENTE[cfg.ambiente]}</span>}
            </p>

            <form onSubmit={submit} className="mt-8 space-y-5" noValidate>
              <div>
                <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-slate-700">E-mail</label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                  <input id="email" type="email" autoComplete="username" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)}
                    placeholder="voce@empresa.com.br"
                    className="h-11 w-full rounded-lg border border-slate-300 bg-white pl-10 pr-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-600 focus:ring-4 focus:ring-blue-600/10" />
                </div>
              </div>
              <div>
                <label htmlFor="senha" className="mb-1.5 block text-sm font-medium text-slate-700">Senha</label>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                  <input id="senha" type={ver ? "text" : "password"} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="h-11 w-full rounded-lg border border-slate-300 bg-white pl-10 pr-11 text-sm outline-none transition placeholder:text-slate-400 focus:border-blue-600 focus:ring-4 focus:ring-blue-600/10" />
                  <button type="button" onClick={() => setVer((v) => !v)} aria-label={ver ? "Ocultar senha" : "Mostrar senha"}
                    className="absolute right-2 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-600">
                    {ver ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
              </div>

              {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

              <button type="submit" disabled={enviando || !cfg || !email || !password}
                className="group flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-blue-700 to-blue-600 text-sm font-semibold text-white shadow-lg shadow-blue-700/25 transition hover:from-blue-800 hover:to-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
                {enviando ? <><Loader2 className="size-4 animate-spin" />Entrando…</> : <>Entrar<ArrowRight className="size-4 transition group-hover:translate-x-0.5" /></>}
              </button>
            </form>

            <div className="mt-8 flex items-center gap-2 border-t border-slate-100 pt-6 text-xs text-slate-500">
              <ShieldCheck className="size-4 text-emerald-600" />
              Conexão protegida. Esqueceu a senha? Fale com o administrador.
            </div>
          </div>
          <p className="mt-8 text-center text-xs text-slate-400 lg:hidden">© {ano} {NOME_SISTEMA}</p>
        </div>
      </section>
    </div>
  );
}
