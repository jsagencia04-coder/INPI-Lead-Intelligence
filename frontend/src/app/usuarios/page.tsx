"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { Select } from "@/components/select";
import { useApi } from "@/components/use-api";
import { api } from "@/lib/api";
import { PAPEL } from "@/lib/auth";
import { fmtDate } from "@/lib/format";

type Usuario = { id: number; email: string; nome: string | null; papel: string; ativo: boolean; ultimo_login: string | null; tem_senha: boolean };

const DESCRICAO: Record<string, string> = {
  leitor: "vê tudo, não altera nada",
  operador: "importa RPI, pesquisa, registra contatos e prospecções, exporta",
  revisor: "aprova leads, confirma contatos, prepara mensagens",
  admin: "usuários, agenda, despachos e jobs avulsos",
};

export default function UsuariosPage() {
  const { data, error, reload } = useApi<Usuario[]>("/api/users");
  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const [senha, setSenha] = useState("");
  const [papel, setPapel] = useState("leitor");
  const [msg, setMsg] = useState<string | null>(null);

  const acao = async (fn: () => Promise<unknown>, ok: string) => {
    setMsg(null);
    try { await fn(); setMsg(ok); reload(); } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  const criar = (e: React.FormEvent) => {
    e.preventDefault();
    acao(async () => {
      await api("/api/users", { method: "POST", body: JSON.stringify({ email, nome: nome || null, papel, senha }) });
      setEmail(""); setNome(""); setSenha("");
    }, "Usuário criado.");
  };
  const mudar = (u: Usuario, corpo: Record<string, unknown>, ok: string) =>
    acao(() => api(`/api/users/${u.id}`, { method: "PATCH", body: JSON.stringify(corpo) }), ok);
  const novaSenha = (u: Usuario) => {
    const s = window.prompt(`Nova senha para ${u.email} (mínimo 10 caracteres, com letras e números):`);
    if (s) mudar(u, { senha: s }, "Senha alterada.");
  };

  return (
    <>
      <PageHeader title="Usuários e permissões" description="Somente administradores. Cada alteração fica registrada na auditoria." />
      <ErrorBox error={error} />
      {msg && <div className="mb-4 rounded-md border bg-muted/40 p-3 text-sm">{msg}</div>}
      <Card className="mb-6">
        <CardHeader><CardTitle className="text-base">Novo usuário</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={criar} className="flex flex-wrap items-end gap-2">
            <Input type="email" placeholder="E-mail" value={email} onChange={(e) => setEmail(e.target.value)} required className="w-64" />
            <Input placeholder="Nome" value={nome} onChange={(e) => setNome(e.target.value)} className="w-48" />
            <Input type="password" placeholder="Senha (mín. 10)" autoComplete="new-password" value={senha} onChange={(e) => setSenha(e.target.value)} required minLength={10} className="w-48" />
            <Select value={papel} onChange={setPapel} options={PAPEL} />
            <Button type="submit">Criar</Button>
          </form>
          <ul className="mt-3 text-xs text-muted-foreground">
            {Object.entries(DESCRICAO).map(([k, d]) => <li key={k}><b>{PAPEL[k]}</b>: {d}</li>)}
          </ul>
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <Table>
            <TableHeader><TableRow><TableHead>E-mail</TableHead><TableHead>Nome</TableHead><TableHead>Perfil</TableHead><TableHead>Situação</TableHead><TableHead>Último acesso</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {data?.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-medium">{u.email}</TableCell>
                  <TableCell>{u.nome ?? "—"}</TableCell>
                  <TableCell><Select value={u.papel} onChange={(v) => mudar(u, { papel: v }, "Perfil alterado.")} options={PAPEL} /></TableCell>
                  <TableCell>{u.ativo ? <Badge variant="outline">ativo</Badge> : <Badge variant="destructive">desativado</Badge>}</TableCell>
                  <TableCell className="text-xs">{u.ultimo_login ? fmtDate(u.ultimo_login) : "nunca"}</TableCell>
                  <TableCell className="space-x-2 text-right">
                    <Button size="sm" variant="outline" onClick={() => novaSenha(u)}>Nova senha</Button>
                    <Button size="sm" variant="outline" onClick={() => mudar(u, { ativo: !u.ativo }, u.ativo ? "Usuário desativado." : "Usuário reativado.")}>{u.ativo ? "Desativar" : "Reativar"}</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </>
  );
}
