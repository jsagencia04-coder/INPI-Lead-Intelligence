import threading

from app import db
from app.jobs import queue
from app.jobs.registry import load_agents
from app.worker import run_one

load_agents()


def test_dedupe_key_evita_job_duplicado():
    with db.transaction("test") as c:
        a = queue.enqueue(c, "system.ping", dedupe_key="rpi:2900")
        b = queue.enqueue(c, "system.ping", dedupe_key="rpi:2900")
    assert a["id"] == b["id"]


def test_claim_concorrente_nao_pega_o_mesmo_job():
    with db.transaction("test") as c:
        for _ in range(20):
            queue.enqueue(c, "system.ping")
    pegos, lock = [], threading.Lock()

    def worker(n):
        while True:
            with db.transaction("test") as c:
                job = queue.claim(c, f"w{n}")
            if job is None:
                return
            with lock:
                pegos.append(job["id"])

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(pegos) == list(range(1, 21))


def test_worker_executa_job_com_sucesso(conn):
    with db.transaction("test") as c:
        job = queue.enqueue(c, "system.ping")
    assert run_one("w-test") is True
    row = conn.execute("select status, resultado from jobs where id = %s", (job["id"],)).fetchone()
    assert row["status"] == "succeeded" and row["resultado"]["pong"] is True
    assert run_one("w-test") is False  # fila vazia


def test_falha_transitoria_faz_retry_com_backoff_e_depois_dead(conn):
    with db.transaction("test") as c:
        job = queue.enqueue(c, "system.ping", {"fail": "transient"}, max_tentativas=2)
    run_one("w")
    row = conn.execute("select status, tentativas, run_after > now() as adiado from jobs").fetchone()
    assert (row["status"], row["tentativas"], row["adiado"]) == ("queued", 1, True)
    conn.execute("update jobs set run_after = now()")
    run_one("w")
    row = conn.execute("select status, ultimo_erro from jobs where id = %s", (job["id"],)).fetchone()
    assert row["status"] == "dead" and "transitória" in row["ultimo_erro"]


def test_falha_permanente_vai_direto_para_dead(conn):
    with db.transaction("test") as c:
        queue.enqueue(c, "system.ping", {"fail": "permanent"})
    run_one("w")
    assert conn.execute("select status, tentativas from jobs").fetchone() == {"status": "dead", "tentativas": 1}


def test_tipo_sem_agente_vai_para_dead(conn):
    with db.transaction("test") as c:
        queue.enqueue(c, "tipo.inexistente")
    run_one("w")
    assert conn.execute("select status from jobs").fetchone()["status"] == "dead"


def test_job_preso_volta_para_fila(conn):
    with db.transaction("test") as c:
        queue.enqueue(c, "system.ping")
        queue.claim(c, "w-morto")
    conn.execute("update jobs set locked_at = now() - interval '2 hours'")
    with db.transaction("test") as c:
        assert queue.requeue_stale(c, 30) == 1
    assert conn.execute("select status from jobs").fetchone()["status"] == "queued"
