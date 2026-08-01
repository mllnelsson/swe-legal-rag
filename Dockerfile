# Local-development image for the whole Python backend. One image, two roles:
# the `pipeline` compose service runs scripts/run_pipeline.py, the `api` service
# runs uvicorn. Both are defined in docker-compose.yml.
#
# Deliberately NOT the Cloud Run image (story 12 will want a leaner one): this
# installs the whole workspace plus the dev dependency group, which is where
# alembic lives, so the container can also apply migrations.
FROM python:3.12-slim

# uv from pip rather than copying from ghcr.io/astral-sh/uv: that would be a
# second base image, and the approved image table in the local-dev playbook has
# no entry for one.
RUN pip install --no-cache-dir uv

# Unbuffered so a one-shot pipeline run streams its progress to `docker logs`
# instead of arriving in blocks.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# The workspace is resolved from the member manifests as well as the root, so
# the dependency layer necessarily includes packages/. Only alembic/ and
# scripts/ changes rebuild cheaply.
COPY pyproject.toml uv.lock README.md ./
COPY packages/ ./packages/
RUN uv sync --frozen --all-packages

COPY alembic.ini ./
# Which model and provider each task uses. Read at startup by every process
# that makes LLM or embedding calls, so a missing copy fails the container.
COPY llm_config.yaml ./
COPY alembic/ ./alembic/
COPY scripts/ ./scripts/

# The project venv on PATH, so `python`, `uvicorn` and `alembic` resolve
# directly — no `uv run` prefix in the compose commands.
ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "scripts/run_pipeline.py"]
