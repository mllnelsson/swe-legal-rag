# Reference

* [Crawl Source — Svenska kyrkan OData API](crawl-source.md) - Authoritative reference for where Överklagandenämnden decisions come from and why the crawl worker is shaped the way it is.
* [GCP Layout and Local Replacements](gcp-layout.md) - The GCP service layout, and the thin-interface abstraction that makes every dependency a config swap between GCP and local dev.
* [Cost Estimate (Idle / Low Usage)](cost-estimate.md) - The idle and low-usage monthly cost breakdown across Cloud SQL, Cloud Run, Pub/Sub, GCS, and usage-based LLM/embedding calls.
* [llm_config.yaml — LLM and Embedding Configuration](llm-config.md) - The single source of truth for which model and provider each LLM role and the embedder use — file format, precedence rules against environment variables, and the full env-var registry.
* [LLM Pricing Prerequisites](llm-pricing.md) - Verified per-token rates and the rules for applying them when analyzing LLM trace records. Reference data, not implemented anywhere in the repo.
* [Decision Document Structure](document-structure.md) - The anatomy of an Överklagandenämnden decision PDF — header, holding, trailer and appendices — and the anchors the pipeline segments it with.
* [Deployment and Data State](deployment-state.md) - What is actually deployed and ingested right now — nothing — and which classes of change are therefore free rather than breaking.
