# Playbooks

* [Local Development Environment](local-dev.md) - How to run the whole system locally — Postgres via Compose on Linux or Homebrew on macOS, application code on the host via uv, optionally in containers — by swapping GCP dependencies for local equivalents via environment variables.
* [Live Testing Guide](live-testing.md) - How to run the system locally end-to-end for manual testing and verification, and how to reset state.
* [Acceptance Walkthrough](acceptance.md) - Turns the PRD's requirements into checks a human performs against the real system — a live agent turn on a real BERGET_API_KEY, against the real ingested corpus — as distinct from the scripted, model-free walkthrough in live testing.
