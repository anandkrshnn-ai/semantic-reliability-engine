---
kind: external_dependency
name: BigQuery — target warehouse with dry-run cost estimation adapter
slug: bigquery
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

BigQuery is one of the target SQL dialects for SCOS contracts and has a dedicated adapter in `adapters/bigquery.py` that performs pre-execution dry runs to estimate compute cost (FinOps). The README references a separate FinOps guide for BigQuery & dbt CI/CD integration. This adapter is experimental scaffolding per the README's AI-assisted development disclosure and should be verified against current Google Cloud SDK APIs before production use.