# Reference

* [Crawl Source — Svenska kyrkan OData API](crawl-source.md) - Authoritative reference for where Överklagandenämnden decisions come from and why the crawl worker is shaped the way it is.
* [GCP Layout and Local Replacements](gcp-layout.md) - The GCP service layout, and the thin-interface abstraction that makes every dependency a config swap between GCP and local dev.
* [Cost Estimate (Idle / Low Usage)](cost-estimate.md) - The idle and low-usage monthly cost breakdown across Cloud SQL, Cloud Run, Pub/Sub, GCS, and usage-based LLM/embedding calls.
* [LLM Pricing Prerequisites](llm-pricing.md) - The pricing rules and verified rate table that back write-time LLM cost tracking (binding for ai/_pricing.py).
* [Decision Document Structure](document-structure.md) - The anatomy of an Överklagandenämnden decision PDF — header, holding, trailer and appendices — and the anchors the pipeline segments it with.
