from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import ai
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import shared
from ai.providers.roles import LLMRole, create_llm_provider
from api.config import AppSettings
from api.routes.chat import router as chat_router
from api.routes.concepts import router as concepts_router
from api.routes.documents import router as documents_router
from api.routes.keywords import router as keywords_router
from api.routes.search import router as search_router
from shared.config import StorageSettings

load_dotenv()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Storage first, then tracing, then anything that makes an API call — the
    # dimension probe below is a real billed embedding and should be recorded
    # like any other.
    app.state.storage = shared.create_storage_backend(StorageSettings())
    ai.install_file_tracing(app.state.storage)

    embedding_provider = ai.create_embedding_provider()

    # Verifying here moves the model load off the first user query and onto startup,
    # and refuses to serve at all on a model/dimension mismatch rather than failing
    # every query. Note this makes container start slower by the model load time —
    # see /decisions/embedding-hosting.md on the unresolved `min-instances`
    # decision.
    await ai.verify_embedding_dimension(embedding_provider)

    app.state.embedding_provider = embedding_provider
    app.state.structured_llm_provider = create_llm_provider(LLMRole.STRUCTURED)
    app.state.chat_llm_provider = create_llm_provider(LLMRole.CHAT)
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

    app.include_router(search_router)
    app.include_router(documents_router)
    app.include_router(concepts_router)
    app.include_router(keywords_router)
    app.include_router(chat_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
