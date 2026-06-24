from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import ai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import shared
from api.config import AppSettings
from api.routes.chat import router as chat_router
from shared.config import StorageSettings


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.embedding_provider = ai.create_embedding_provider()
    app.state.storage = shared.create_storage_backend(StorageSettings())
    yield


def create_app() -> FastAPI:
    settings = AppSettings()
    app = FastAPI(lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
