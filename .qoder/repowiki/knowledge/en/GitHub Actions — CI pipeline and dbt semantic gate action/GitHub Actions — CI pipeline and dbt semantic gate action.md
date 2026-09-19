---
kind: external_dependency
name: GitHub Actions — CI pipeline and dbt semantic gate action
slug: github-actions
category: external_dependency
category_hints:
    - client_constraint
scope:
    - '**'
---

The repository ships two GitHub Actions workflows: a general CI workflow (`ci.yml`) and a `sre-dbt-semantic-gate.yml` intended to serve as a GitHub Marketplace Action wedge for analytics engineering teams. The README promotes publishing this as a distributable action. The CI badge links to `anandkrshnn-ai/semantic-reliability-engine`, indicating the canonical owner org for published artifacts.