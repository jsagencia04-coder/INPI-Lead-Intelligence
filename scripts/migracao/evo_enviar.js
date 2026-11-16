// Envio da Evolution do INPI (roda na ORIGEM, dentro do container da Evolution, que tem node, pg e tar).
//   node evo_enviar.js banco       lê /tmp/evo.dump (gerado por pg_dump no container do banco) via pg_read_binary_file
//   node evo_enviar.js instancias  tar.gz de /evolution/instances (sessão do WhatsApp)
// Variáveis: DESTINO (https://<host>/_migracao), MIGRACAO_TOKEN; DATABASE_CONNECTION_URI já existe no container.
// Saída sem segredos: só nome, bytes e sha256.
const https = require("https");
const crypto = require("crypto");
const { spawn } = require("child_process");
const { Client } = require("pg");

function put(nome, produtor) {
  return new Promise((ok, falha) => {
    const h = crypto.createHash("sha256");
    const u = new URL(`${process.env.DESTINO}/arquivo/${nome}`);
    const req = https.request(u, { method: "PUT", headers: { "X-Token": process.env.MIGRACAO_TOKEN, "Transfer-Encoding": "chunked" } }, (res) => {
      let b = "";
      res.on("data", (d) => (b += d));
      res.on("end", () => {
        if (res.statusCode !== 200) return falha(new Error(`HTTP ${res.statusCode}`));
        const r = JSON.parse(b);
        if (r.sha256 !== h.digest("hex")) return falha(new Error(`${nome}: sha256 diferente no destino`));
        ok(r);
      });
    });
    req.on("error", falha);
    produtor((chunk) => { h.update(chunk); return new Promise((r) => (req.write(chunk) ? r() : req.once("drain", r))); })
      .then(() => req.end(), falha);
  });
}

async function banco() {
  const c = new Client({ connectionString: process.env.DATABASE_CONNECTION_URI.replace(/\?.*$/, "") });
  await c.connect();
  const tam = Number((await c.query("select (pg_stat_file('/tmp/evo.dump')).size as s")).rows[0].s);
  const r = await put("evo.dump", async (w) => {
    for (let o = 0; o < tam; o += 4 << 20) {
      const { rows } = await c.query("select pg_read_binary_file('/tmp/evo.dump', $1, $2) as b", [o, Math.min(4 << 20, tam - o)]);
      await w(rows[0].b);
    }
  });
  await c.end();
  console.log(JSON.stringify(r));
}

async function instancias() {
  const tar = spawn("tar", ["czf", "-", "-C", "/evolution/instances", "."]);
  const r = await put("evo_instances.tar.gz", async (w) => {
    for await (const chunk of tar.stdout) await w(chunk);
    const code = await new Promise((r) => (tar.exitCode !== null ? r(tar.exitCode) : tar.on("close", r)));
    if (code !== 0) throw new Error(`tar saiu com ${code}`);
  });
  console.log(JSON.stringify(r));
}

({ banco, instancias })[process.argv[2]]().catch((e) => { console.error("ERRO", e.message); process.exit(1); });
