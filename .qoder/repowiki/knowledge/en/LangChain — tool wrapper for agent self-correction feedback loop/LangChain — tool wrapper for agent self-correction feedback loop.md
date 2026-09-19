---
kind: external_dependency
name: LangChain — tool wrapper for agent self-correction feedback loop
slug: langchain
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
---

The LangChain integration exposes `SREGuardrailToolWrapper`, which wraps any existing LangChain SQL tool so that generated queries are evaluated by the SCOS guardrail before execution. When `raise_on_drift=False`, violations are returned as structured feedback into the agent's scratchpad to enable self-correction retries rather than hard-blocking. This is an optional integration path; the core engine does not depend on LangChain.