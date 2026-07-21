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
    embedding_provider = ai.create_embedding_provider()

    # Verifying here moves the model load off the first user query and onto startup,
    # and refuses to serve at all on a model/dimension mismatch rather than failing
    # every query. Note this makes container start slower by the model load time —
    # see EMBEDDING_HOSTING.md on the unresolved `min-instances` decision.
    await ai.verify_embedding_dimension(embedding_provider)

    app.state.embedding_provider = embedding_provider
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
