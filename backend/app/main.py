"""API FastAPI.

uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import comercial, db, security
from app.api import (
    auth_routes,
    comercial_routes,
    consent_routes,
    contact_routes,
    lead_routes,
    mapa_routes,
    office_routes,
    pipeline_routes,
    primeiro_contato_routes,
    rpi_routes,
    servicos_routes,
    whatsapp_routes,
)
from app.api.routes import public, router
from app.config import get_settings
from app.jobs.registry import load_agents


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if problemas := security.problemas_de_configuracao(settings):
        raise RuntimeError("Configuração insegura, a API não vai iniciar:\n- " + "\n- ".join(problemas))
    load_agents()
    with db.transaction("system:startup") as conn:
        security.conferir_ambiente(conn, settings)
        security.bootstrap_admin(conn, settings)
        comercial.sincronizar_config(conn, settings)
    yield
    db.close_pool()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="INPI Lead Intelligence", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(public)
    app.include_router(auth_routes.public)
    app.include_router(auth_routes.router)
    app.include_router(router)
    app.include_router(rpi_routes.router)
    app.include_router(lead_routes.router)
    app.include_router(contact_routes.router)
    app.include_router(consent_routes.router)
    app.include_router(pipeline_routes.router)
    app.include_router(mapa_routes.router)
    app.include_router(servicos_routes.router)
    app.include_router(comercial_routes.router)
    app.include_router(whatsapp_routes.router)
    app.include_router(whatsapp_routes.webhook)
    app.include_router(primeiro_contato_routes.router)
    app.include_router(primeiro_contato_routes.webhook)
    app.include_router(office_routes.router)
    app.include_router(office_routes.ws_router)
    return app


app = create_app()
