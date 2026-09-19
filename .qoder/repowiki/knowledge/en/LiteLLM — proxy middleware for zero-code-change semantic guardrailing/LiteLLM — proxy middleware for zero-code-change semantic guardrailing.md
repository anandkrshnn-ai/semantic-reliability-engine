---
kind: external_dependency
name: LiteLLM — proxy middleware for zero-code-change semantic guardrailing
slug: litellm
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
---

The LiteLLM integration provides `SRELiteLLMGuardrail`, registered as a LiteLLM callback so that every LLM request routed through the enterprise proxy is intercepted and validated against SCOS contracts before being forwarded to the underlying provider (OpenAI, Anthropic, Ollama, etc.). This enables deployment as a sidecar or proxy-level gate without modifying application code.