"""LiteLLM Custom Guardrail Integration for Semantic Reliability Engine (SRE)."""

import re
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import logging

from semantic_reliability.guardrail import SemanticGuardrail, GuardrailResult, SemanticDriftException

logger = logging.getLogger("sre.integrations.litellm")


class SRELiteLLMGuardrail:
    """
    LiteLLM-compatible guardrail hook for proxying and validating LLM-generated SQL queries.

    Can be registered directly as a custom guardrail or post-call hook in LiteLLM:
    ```python
    import litellm
    from semantic_reliability.integrations.litellm import SRELiteLLMGuardrail

    guardrail = SRELiteLLMGuardrail(contract_path="contracts/net_revenue.yaml")
    litellm.callbacks = [guardrail]
    ```
    """

    def __init__(
        self,
        contract_path: Union[str, Path],
        metric_id: Optional[str] = None,
        dialect: str = "duckdb",
        block_on_violation: bool = True,
    ):
        self.guardrail = SemanticGuardrail.from_contract(contract_path)
        self.metric_id = metric_id
        self.dialect = dialect
        self.block_on_violation = block_on_violation

    def _extract_sql_from_response(self, response_obj: Any) -> Optional[str]:
        """Extract SQL string from LiteLLM response or tool call payload."""
        try:
            # Check choices content
            if hasattr(response_obj, "choices") and response_obj.choices:
                choice = response_obj.choices[0]
                message = getattr(choice, "message", None)
                if message:
                    # Check tool calls
                    if hasattr(message, "tool_calls") and message.tool_calls:
                        for tool_call in message.tool_calls:
                            args = getattr(tool_call.function, "arguments", "")
                            match = re.search(r"SELECT\s+.+?FROM\s+.+?", args, re.IGNORECASE | re.DOTALL)
                            if match:
                                return match.group(0)

                    # Check text content for markdown SQL code blocks
                    content = getattr(message, "content", "")
                    if content:
                        code_block = re.search(r"```(?:sql)?\s*(SELECT\s+[\s\S]+?)\s*```", content, re.IGNORECASE)
                        if code_block:
                            return code_block.group(1).strip()
                        if "SELECT" in content.upper() and "FROM" in content.upper():
                            return content.strip()

            elif isinstance(response_obj, dict):
                content = str(response_obj)
                code_block = re.search(r"```(?:sql)?\s*(SELECT\s+[\s\S]+?)\s*```", content, re.IGNORECASE)
                if code_block:
                    return code_block.group(1).strip()
        except Exception as e:
            logger.debug(f"Could not extract SQL from response: {e}")
        return None

    def post_call_success_hook(
        self,
        data: Dict[str, Any],
        user_api_key_dict: Dict[str, Any],
        response: Any,
    ) -> Any:
        """Synchronous LiteLLM hook executed after completion."""
        sql = self._extract_sql_from_response(response)
        if sql:
            result = self.guardrail.verify(sql, metric_id=self.metric_id, dialect=self.dialect)
            if not result.is_valid and self.block_on_violation:
                raise SemanticDriftException(result)
        return response

    async def async_post_call_success_hook(
        self,
        data: Dict[str, Any],
        user_api_key_dict: Dict[str, Any],
        response: Any,
    ) -> Any:
        """Asynchronous LiteLLM hook."""
        return self.post_call_success_hook(data, user_api_key_dict, response)
