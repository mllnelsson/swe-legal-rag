"""Berget-hosted embedding provider (OpenAI-compatible embeddings endpoint)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from llm_core import (
    LLMOperation,
    Usage,
    finish_trace,
    start_trace,
    trace_context,
    trace_failure,
    trace_result,
)

if TYPE_CHECKING:
    from ai.embedding import EmbeddingConfig

# Embedding runs once per chunk over the whole corpus, so it is plausibly the
# largest single line of token spend — it is traced for the same reason chat is.
SOURCE = "ai.embed"

# The embedded texts themselves are deliberately not recorded. They are chunk
# text already durable in Postgres and reachable from the document id; copying
# the corpus into the trace stream would multiply its size for no new
# information. This is the one place tracing does not keep the full input.


def _usage_from_embeddings(usage: Any) -> Usage | None:
    if usage is None:
        return None
    return Usage(
        input_tokens=getattr(usage, "prompt_tokens", None),
        # An embedding response has no generated tokens; None says "not
        # reported", which is the truth, rather than implying a zero.
        output_tokens=None,
        total_tokens=getattr(usage, "total_tokens", None),
    )


class BergetEmbeddingProvider:
    def __init__(self, config: EmbeddingConfig, *, default_base_url: str) -> None:
        from openai import AsyncOpenAI

        if not config.berget_api_key:
            raise ValueError("berget_api_key is required for BergetEmbeddingProvider")

        self._client = AsyncOpenAI(
            api_key=config.berget_api_key,
            base_url=config.base_url or default_base_url,
        )
        self._model = config.model
        self._provider_name = config.provider

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        with trace_context(
            source=SOURCE,
            texts_count=len(texts),
            input_chars=sum(len(text) for text in texts),
        ):
            trace = start_trace(LLMOperation.embed, [])
            try:
                response = await self._client.embeddings.create(
                    model=self._model, input=texts
                )
            except BaseException as exc:
                trace_failure(trace, exc)
                finish_trace(trace)
                raise

            trace_result(
                trace,
                usage=_usage_from_embeddings(getattr(response, "usage", None)),
                model=getattr(response, "model", None) or self._model,
                provider=self._provider_name,
            )
            finish_trace(trace)

        return [d.embedding for d in response.data]
