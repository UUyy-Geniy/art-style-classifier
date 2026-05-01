from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from artstyle_backend.api.router import api_router
from artstyle_backend.core.config import get_settings
from artstyle_backend.core.database import SessionLocal, engine
from artstyle_backend.messaging.publisher import RabbitMQPublisher
from artstyle_backend.services.bootstrap import ensure_seed_data
from artstyle_backend.services.storage import StorageService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    publisher = RabbitMQPublisher(settings)
    await publisher.connect()

    app.state.publisher = publisher
    app.state.storage = StorageService(settings)

    async with SessionLocal() as session:
        await ensure_seed_data(session)

    try:
        yield
    finally:
        await publisher.close()
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Art Style Classifier Backend",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()
