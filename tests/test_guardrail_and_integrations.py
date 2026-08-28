import pytest
from pathlib import Path

from semantic_reliability import SemanticGuardrail, GuardrailResult, SemanticDriftException
from semantic_reliability.integrations.langchain import SREGuardrailToolWrapper, SREGuardrailCallback
from semantic_reliability.integrations.litellm import SRELiteLLMGuardrail

CONTRACT_PATH = Path("benchmark_corpus/dev/net_revenue/contract.yaml")

VALID_NET_REV_SQL = """
SELECT
    customer_id,
    DATE_TRUNC('month', transaction_date) AS reporting_month,
    SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
    SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
FROM transactions
WHERE region = 'NA' AND status = 'active'
GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
"""


def test_guardrail_from_contract_file():
    guard = SemanticGuardrail.from_contract(CONTRACT_PATH)
    assert guard.primary_metric == "net_revenue"

    res = guard.verify(VALID_NET_REV_SQL)
    assert isinstance(res, GuardrailResult)
    assert res.is_valid is True
    assert res.drift_score == 0.0
    assert len(res.violations) == 0


def test_guardrail_detects_filter_violation():
    guard = SemanticGuardrail.from_contract(CONTRACT_PATH)

    # Invalid SQL missing the required region = 'NA' and invoice/refund conditions
    invalid_sql = "SELECT SUM(amount) FROM transactions WHERE status = 'active'"
    res = guard.verify(invalid_sql)

    assert res.is_valid is False
    assert res.drift_score > 0.0
    assert len(res.violations) > 0


def test_guardrail_intercept():
    guard = SemanticGuardrail.from_contract(CONTRACT_PATH)

    intercepted = guard.intercept(VALID_NET_REV_SQL)
    assert intercepted == VALID_NET_REV_SQL

    invalid_sql = "SELECT SUM(amount) FROM transactions"
    with pytest.raises(SemanticDriftException) as exc_info:
        guard.intercept(invalid_sql)
    assert "Semantic Guardrail Blocked Execution" in str(exc_info.value)


def test_langchain_tool_wrapper_self_correction_feedback():
    class MockSQLTool:
        name = "sql_db_query"
        description = "Execute an SQL query against the database."

        def run(self, tool_input: str) -> str:
            return "RESULT: 150000.00"

    mock_tool = MockSQLTool()
    guarded_tool = SREGuardrailToolWrapper(
        base_tool=mock_tool,
        contract_path=CONTRACT_PATH,
        raise_on_drift=False,
    )

    # Valid query executes through
    out = guarded_tool.run(VALID_NET_REV_SQL)
    assert out == "RESULT: 150000.00"

    # Invalid query returns error string with guidance rather than raising
    invalid_sql = "SELECT SUM(amount) FROM transactions"
    out_err = guarded_tool.run(invalid_sql)
    assert "ERROR [SEMANTIC_GUARDRAIL_BLOCKED]" in out_err
    assert "net_revenue" in out_err


def test_langchain_tool_wrapper_raise_on_drift():
    class MockSQLTool:
        def run(self, tool_input: str) -> str:
            return "SUCCESS"

    guarded_tool = SREGuardrailToolWrapper(
        base_tool=MockSQLTool(),
        contract_path=CONTRACT_PATH,
        raise_on_drift=True,
    )

    with pytest.raises(SemanticDriftException):
        guarded_tool.run("SELECT SUM(amount) FROM transactions")


def test_litellm_guardrail_hook():
    guardrail = SRELiteLLMGuardrail(contract_path=CONTRACT_PATH, block_on_violation=True)

    class MockChoice:
        class Message:
            content = f"Here is the query:\n```sql\n{VALID_NET_REV_SQL}\n```"
        message = Message()

    class MockResponse:
        choices = [MockChoice()]

    # Valid response passes through
    res = guardrail.post_call_success_hook(data={}, user_api_key_dict={}, response=MockResponse())
    assert res is not None

    # Invalid response triggers exception
    class MockInvalidChoice:
        class Message:
            content = "```sql\nSELECT SUM(amount) FROM transactions\n```"
        message = Message()

    class MockInvalidResponse:
        choices = [MockInvalidChoice()]

    with pytest.raises(SemanticDriftException):
        guardrail.post_call_success_hook(data={}, user_api_key_dict={}, response=MockInvalidResponse())
