"""Jobs de sistema. `system.ping` valida o caminho completo API -> fila -> worker.

Os agentes reais (rpi.collect, rpi.parse, inpi.verify, research.*, lead.*, sales.*)
são adicionados nas fases seguintes, cada um no seu módulo dentro de app/agents/.
"""

from app.jobs.registry import JobContext, PermanentError, handler


@handler("system.ping")
def ping(conn, ctx: JobContext) -> dict:
    if ctx.payload.get("fail") == "permanent":
        raise PermanentError("falha permanente simulada")
    if ctx.payload.get("fail") == "transient":
        raise RuntimeError("falha transitória simulada")
    db_now = conn.execute("select now() as agora").fetchone()["agora"]
    return {"pong": True, "worker": ctx.worker_id, "db_now": db_now.isoformat()}
