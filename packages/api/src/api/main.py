from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import agents
import ai
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import shared
from ai.providers.roles import LLMRole, create_llm_provider
from api.config import AppSettings
from api.correlation import INTERACTION_ID_HEADER
from api.routes.chat import router as chat_router
from api.routes.concepts import router as concepts_router
from api.routes.documents import router as documents_router
from api.routes.keywords import router as keywords_router
from api.routes.search import router as search_router
from api.routes.sessions import router as sessions_router
from api.routes.sql import router as sql_router
from shared.config import StorageSettings

load_dotenv()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # First, because it is pure file and metadata work and costs nothing to
    # fail. Fatal by design: semantic_model.yaml supplies the SQL agent's table
    # allow-list and its grounding policy, not merely its prose, so there is no
    # reduced mode worth serving. Also warms the cache, so no request pays the
    # file read. See /reference/semantic-model.md.
    agents.check_semantic_model()

    # Tracing before anything that makes an API call — the dimension probe below
    # is a real billed embedding and should be recorded like any other. It takes
    # no storage backend: traces are local files, not blobs.
    ai.install_file_tracing()

    app.state.storage = shared.create_storage_backend(StorageSettings())

    embedding_provider = ai.create_embedding_provider()

    # Verifying here moves the model load off the first user query and onto startup,
    # and refuses to serve at all on a model/dimension mismatch rather than failing
    # every query. Note this makes container start slower by the model load time —
    # see /decisions/embedding-hosting.md on the unresolved `min-instances`
    # decision.
    await ai.verify_embedding_dimension(embedding_provider)

    app.state.embedding_provider = embedding_provider
    app.state.structured_llm_provider = create_llm_provider(LLMRole.STRUCTURED)
    # The conversational agent uses both: CHAT drives its tool loop and writes
    # the answer, READ is the sub-agent it hands a whole decision to.
    app.state.chat_llm_provider = create_llm_provider(LLMRole.CHAT)
    app.state.read_llm_provider = create_llm_provider(LLMRole.READ)
    app.state.sql_llm_provider = create_llm_provider(LLMRole.SQL)
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
        # A browser cannot read a response header that is not exposed, however
        # permissive `allow_headers` is — that governs the request direction
        # only. Without this the correlation id reaches the browser and stays
        # invisible to it.
        expose_headers=[INTERACTION_ID_HEADER],
    )

    app.include_router(search_router)
    app.include_router(documents_router)
    app.include_router(concepts_router)
    app.include_router(keywords_router)
    app.include_router(sql_router)
    app.include_router(chat_router)
    app.include_router(sessions_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
