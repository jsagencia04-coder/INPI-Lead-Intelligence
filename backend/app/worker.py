"""Worker dos agentes.

Uso:
    python -m app.worker                 # loop contínuo
    python -m app.worker --once          # processa até esvaziar a fila e sai
    python -m app.worker --tipos rpi.collect rpi.parse

Cada job roda na sua própria transação: se o handler falhar, nada do que ele
escreveu é gravado (atomicidade), e a falha é registrada em seguida.
"""

import argparse
import logging
import signal
import time
import traceback

from app import comercial, db
from app.config import get_settings
from app.jobs import queue, scheduler
from app.jobs.registry import JobContext, PermanentError, RetryLater, get_handler, get_on_dead, load_agents

log = logging.getLogger("worker")
_stop = False


def _handle_signal(*_):
    global _stop
    _stop = True


def run_one(worker_id: str, tipos: list[str] | None = None) -> bool:
    """Processa um job. Retorna False se a fila estava vazia."""
    with db.transaction(f"worker:{worker_id}") as conn:
        job = queue.claim(conn, worker_id, tipos)
    if job is None:
        return False

    ctx = JobContext(job=job, worker_id=worker_id)
    fn = get_handler(job["tipo"])
    log.info("job %s (%s) tentativa %s", job["id"], job["tipo"], job["tentativas"])
    try:
        if fn is None:
            raise PermanentError(f"Nenhum agente registrado para o tipo '{job['tipo']}'")
        with db.transaction(ctx.actor) as conn:
            resultado = fn(conn, ctx)
            queue.complete(conn, job["id"], resultado)
        log.info("job %s concluído", job["id"])
    except Exception as exc:  # noqa: BLE001
        retryable = not isinstance(exc, PermanentError)
        detalhe = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}"
        with db.transaction(f"worker:{worker_id}") as conn:
            delay = exc.delay_seconds if isinstance(exc, RetryLater) else None
            status = queue.fail(conn, job["id"], detalhe, retryable=retryable, delay_seconds=delay)
            if status == "dead" and (hook := get_on_dead(job["tipo"])):
                hook(conn, job, f"{type(exc).__name__}: {exc}")
        log.warning("job %s falhou (%s): %s", job["id"], status, exc)
    return True


def run_scheduler(worker_id: str) -> None:
    try:
        with db.transaction(f"scheduler:{worker_id}") as conn:
            if criados := scheduler.tick(conn):
                log.info("agendador enfileirou job(s) %s", criados)
    except Exception:  # noqa: BLE001 - o agendador nunca derruba o worker
        log.exception("falha no agendador")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--tipos", nargs="*")
    parser.add_argument("--no-scheduler", action="store_true", help="não disparar os agendamentos")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = get_settings()
    load_agents()
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    with db.transaction(f"worker:{settings.worker_id}") as conn:
        n = queue.requeue_stale(conn, settings.job_lock_timeout_minutes)
        comercial.sincronizar_config(conn, settings)
        if n:
            log.warning("%s job(s) presos devolvidos à fila", n)

    while not _stop:
        if not args.no_scheduler:
            run_scheduler(settings.worker_id)
        worked = run_one(settings.worker_id, args.tipos)
        if not worked:
            if args.once:
                break
            time.sleep(settings.worker_poll_seconds)
    db.close_pool()


if __name__ == "__main__":
    main()
