from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import agents
import ai
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import shared
from ai.providers.roles import LLMRole, create_llm_provider
from api.access_log import AccessLogMiddleware
from api.config import AppSettings
from api.correlation import INTERACTION_ID_HEADER
from api.logging_setup import configure_api_logging
from api.routes.chat import router as chat_router
from api.routes.concepts import router as concepts_router
from api.routes.documents import router as documents_router
from api.routes.keywords import router as keywords_router
from api.routes.search import router as search_router
from api.routes.sessions import router as sessions_router
from api.routes.sql import router as sql_router
from shared.config import StorageSettings
from shared.logging_config import resolve_log_level

# Order matters and is not incidental. `load_dotenv` first, because LOG_LEVEL may
# live in `.env`. Logging second, because the router imports below can log and
# `create_app()` certainly does. Both at import rather than from a `main()`,
# because `uvicorn api.main:app` makes this module's import the entry point —
# there is no function for the entry point to be. uvicorn has already applied its
# own dictConfig by the time it imports us, so the `force=True` inside wins.
load_dotenv()
configure_api_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    started_at = time.perf_counter()

    # First, because it is pure file and metadata work and costs nothing to
    # fail. Fatal by design: semantic_model.yaml supplies the SQL agent's table
    # allow-list and its grounding policy, not merely its prose, so there is no
    # reduced mode worth serving. Also warms the cache, so no request pays the
    # file read. See /reference/semantic-model.md.
    agents.check_semantic_model()
    logger.debug("Semantic model checked")

    # Tracing before anything that makes an API call — the dimension probe below
    # is a real billed embedding and should be recorded like any other. It takes
    # no storage backend: traces are local files, not blobs.
    ai.install_file_tracing()

    storage_settings = StorageSettings()
    app.state.storage = shared.create_storage_backend(storage_settings)
    logger.debug("Storage backend ready: %s", storage_settings.storage_backend)

    embedding_provider = ai.create_embedding_provider()

    # Verifying here moves the model load off the first user query and onto startup,
    # and refuses to serve at all on a model/dimension mismatch rather than failing
    # every query. Note this makes container start slower by the model load time —
    # see /decisions/embedding-hosting.md on the unresolved `min-instances`
    # decision. The timing is logged because a warm-cache local model still costs
    # ~9s here, and a cold or revalidating one ~90s, which reads as a hang —
    # see /playbooks/local-dev.md.
    embedding_started_at = time.perf_counter()
    dimension = await ai.verify_embedding_dimension(embedding_provider)
    logger.debug(
        "Embedding provider ready in %.1fs: dimension=%d",
        time.perf_counter() - embedding_started_at,
        dimension,
    )

    app.state.embedding_provider = embedding_provider
    app.state.structured_llm_provider = create_llm_provider(LLMRole.STRUCTURED)
    # The conversational agent uses four: CHAT plans the turn and writes the
    # answer, ORCHESTRATE runs the tool loop between them, READ is the sub-agent
    # it hands a whole decision to, and SQL answers its counting questions.
    app.state.chat_llm_provider = create_llm_provider(LLMRole.CHAT)
    app.state.orchestrate_llm_provider = create_llm_provider(LLMRole.ORCHESTRATE)
    app.state.read_llm_provider = create_llm_provider(LLMRole.READ)
    app.state.sql_llm_provider = create_llm_provider(LLMRole.SQL)
    logger.debug(
        "LLM providers built for roles: structured, chat, orchestrate, read, sql"
    )

    logger.info(
        "API ready in %.1fs — storage=%s embedding_dimension=%d log_level=%s",
        time.perf_counter() - started_at,
        storage_settings.storage_backend,
        dimension,
        logging.getLevelName(resolve_log_level()),
    )
    yield
    logger.info("API shutting down")


def create_app() -> FastAPI:
    settings = AppSettings()
    app = FastAPI(lifespan=_lifespan)

    # Read bottom-up: `add_middleware` inserts at the front, so the middleware
    # added *last* ends up outermost. CORS therefore wraps the access log, which
    # is deliberate — CORS answers preflight OPTIONS itself, and those never
    # reaching the access log is how the log stays free of them without a
    # method check.
    app.add_middleware(AccessLogMiddleware)

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
