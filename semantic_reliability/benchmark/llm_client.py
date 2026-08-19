"""LLM Provider Client for Live Agent Benchmark Evaluation.
Supports OpenAI, Anthropic, Ollama, and OpenAI-compatible endpoints (vLLM, LiteLLM).
"""
import os
import json
import logging
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger("sre.benchmark.llm")


class LiveLLMClient:
    """Standard client for invoking live LLMs with tools or JSON mode."""

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: float = 0.0,
    ):
        self.provider = provider.lower()
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        self.api_base = api_base or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.temperature = temperature

    def __call__(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Invokes the selected LLM provider and returns structured response."""
        import requests

        if self.provider in ("openai", "ollama", "vllm", "litellm"):
            headers = {
                "Authorization": f"Bearer {self.api_key or 'sk-no-key-required'}",
                "Content-Type": "application/json",
            }
            url = f"{self.api_base.rstrip('/')}/chat/completions"
            payload: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
            }
            if tools:
                payload["tools"] = tools

            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]["message"]
            return {
                "role": "assistant",
                "content": choice.get("content"),
                "tool_calls": choice.get("tool_calls", []),
            }

        elif self.provider == "anthropic":
            headers = {
                "x-api-key": self.api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            url = f"{self.api_base.rstrip('/') if self.api_base != 'https://api.openai.com/v1' else 'https://api.anthropic.com'}/v1/messages"
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
            user_msgs = [m for m in messages if m["role"] != "system"]

            payload = {
                "model": self.model,
                "system": system_msg,
                "messages": user_msgs,
                "max_tokens": 2048,
                "temperature": self.temperature,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            content_text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            return {
                "role": "assistant",
                "content": content_text,
                "tool_calls": [],
            }

        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")
