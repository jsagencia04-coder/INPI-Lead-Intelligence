# Publicar pelo EasyPanel (mesma VPS de outros sistemas)

O EasyPanel já ocupa as portas 80 e 443 e cuida do HTTPS. Por isso, nesta VPS **não** se usa o
`docker-compose.web.yml` (que traz o Caddy), e sim o `docker-compose.easypanel.yml`.

## 1. Criar o serviço
1. No EasyPanel: **Create Project** (ex.: `inpi`).
2. Dentro do projeto: **+ Service → Compose**. Nome: `sistema`.
3. Em **Source**, escolha **Git** (ou GitHub):
   - Repositório: `git@github.com:jsagencia04-coder/INPI-Lead-Intelligence.git`, branch `main`
   - Compose file: `docker-compose.easypanel.yml`
   - Como o repositório é privado, o EasyPanel mostra uma **chave SSH pública**: cadastre-a no GitHub em
     Settings → Deploy keys do repositório (sem permissão de escrita).

## 2. Variáveis (aba Environment)
```
POSTGRES_PASSWORD=<só letras e números, longa>
APP_SECRET_KEY=<64 caracteres aleatórios>
APP_ENV=homologacao
AUTH_MODE=local
BOOTSTRAP_ADMIN_EMAIL=seu@email.com.br
BOOTSTRAP_ADMIN_PASSWORD=<10+ caracteres, letras e números>
DOMINIO=<o domínio definido no passo 3, sem https://>
```
Para gerar valores aleatórios, no Web console da VPS: `openssl rand -hex 24` e `openssl rand -hex 32`.

## 3. Domínio (aba Domains)
Adicione um domínio apontando para o serviço **`web`**, porta **`3000`**, com HTTPS ligado.
Pode ser o domínio gratuito que o EasyPanel oferece ou `srv2078053.hstgr.cloud`.

## 4. Deploy
Clique em **Deploy**. A primeira construção leva de 5 a 15 minutos neste plano (1 processador).
Acompanhe em **Logs**. Ao terminar, abra o domínio e entre com o administrador.

Depois do primeiro acesso, troque a senha e apague `BOOTSTRAP_ADMIN_PASSWORD` da aba Environment.

## 5. Atualizações
A cada `git push`, clique em **Deploy** de novo, ou ligue o **Auto Deploy** (o EasyPanel fornece um
endereço de webhook para cadastrar no GitHub em Settings → Webhooks). Os dados ficam em volumes e não
são tocados; as migrations entram sozinhas.

## Cuidados
- Antes de atualizar, faça backup do banco (o EasyPanel tem console por serviço):
  `pg_dump -U postgres inpi > /tmp/backup.sql` no serviço `db`.
- Memória: a VPS tem 4 GB divididos com os outros sistemas. Se a construção falhar por falta de
  memória, pare temporariamente outro serviço ou aumente o plano.
- A base CNPJ da Receita ocupa cerca de 8 GB de disco.
