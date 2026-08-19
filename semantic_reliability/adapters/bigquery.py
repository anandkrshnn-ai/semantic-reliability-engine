"""BigQuery Dry-Run Adapter with configurable pricing and strict safety controls."""
import hashlib
import time
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import sqlglot

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.compiler.contracts import SemanticContractValidator


class BigQueryPricingPolicy(BaseModel):
    """Configurable BigQuery on-demand analysis pricing model."""
    billing_unit: str = "TiB"
    price_per_tib_usd: float = 6.25  # Standard GCP on-demand rate per TiB (1024^4 bytes)
    monthly_free_tib: float = 1.0
    region: str = "US"
    maximum_bytes_billed: Optional[int] = None  # Byte budget ceiling
    require_project_id: bool = False
    allow_execution: bool = False  # Hard safety gate: must remain False for dry runs


class BigQueryDryRunAdapter:
    """Validates SQL against BigQuery dry-run API and SRE Semantic Contracts without data scanning."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        credentials=None,
        client=None,
        policy: Optional[BigQueryPricingPolicy] = None,
    ):
        self.project_id = project_id
        self.credentials = credentials
        self._client = client
        self.policy = policy or BigQueryPricingPolicy()

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from google.cloud import bigquery
            self._client = bigquery.Client(project=self.project_id, credentials=self.credentials)
            return self._client
        except Exception:
            return None

    def evaluate(
        self,
        sql: str,
        metric_def: MetricDefinition,
        dialect: str = "bigquery",
        mock_bytes_processed: Optional[int] = None,
        mock_api_latency_ms: Optional[float] = None,
        apply_free_tier: bool = False,
    ) -> Dict[str, Any]:
        t_start_ast = time.perf_counter()
        sql_hash = hashlib.sha256(sql.strip().encode("utf-8")).hexdigest()

        # Step 0: Policy validation
        if self.policy.require_project_id and not self.project_id:
            return {
                "engine": "bigquery",
                "execution_mode": "policy_denied",
                "sql_hash": sql_hash,
                "contract_id": metric_def.metric,
                "bytes_processed": 0,
                "cost_estimate": None,
                "contract_compliant": False,
                "violations": [],
                "bq_error": "Policy violation: project_id is required but was not provided.",
                "decision": "DENY",
                "local_ast_latency_ms": 0.0,
                "dry_run_api_latency_ms": 0.0,
            }

        # Step 1: Local AST & Contract Validation
        try:
            sqlglot.parse_one(sql, read=dialect)
            eval_res = SemanticContractValidator.validate(candidate_sql=sql, metric_def=metric_def, dialect=dialect)
            violations = [f"{v.invariant_category}: {v.invariant_rule}" for v in eval_res.violations]
            contract_compliant = eval_res.passed
        except Exception as e:
            ast_lat = (time.perf_counter() - t_start_ast) * 1000.0
            return {
                "engine": "bigquery",
                "execution_mode": "parse_failed",
                "sql_hash": sql_hash,
                "contract_id": metric_def.metric,
                "bytes_processed": 0,
                "cost_estimate": None,
                "contract_compliant": False,
                "violations": [],
                "bq_error": f"SQLGlot parse error: {str(e)}",
                "decision": "DENY",
                "local_ast_latency_ms": round(ast_lat, 2),
                "dry_run_api_latency_ms": 0.0,
            }

        ast_latency_ms = (time.perf_counter() - t_start_ast) * 1000.0

        # Step 2: BigQuery Dry-Run API Call
        bytes_processed = 0
        execution_mode = "dry_run"
        bq_error = None
        t_start_api = time.perf_counter()

        if mock_bytes_processed is not None:
            bytes_processed = mock_bytes_processed
            api_latency_ms = mock_api_latency_ms if mock_api_latency_ms is not None else 12.5
        else:
            client = self._get_client()
            if client is not None:
                try:
                    from google.cloud import bigquery
                    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
                    query_job = client.query(sql, job_config=job_config)
                    bytes_processed = query_job.total_bytes_processed or 0
                    api_latency_ms = (time.perf_counter() - t_start_api) * 1000.0
                except Exception as e:
                    execution_mode = "dry_run_failed"
                    bq_error = str(e)
                    api_latency_ms = (time.perf_counter() - t_start_api) * 1000.0
            else:
                execution_mode = "dry_run_simulated"
                bytes_processed = 10 * 1024 * 1024
                api_latency_ms = 0.0

        # Step 3: Cost Calculation & Budget Enforcement
        tib_processed = bytes_processed / (1024 ** 4)
        gross_cost = tib_processed * self.policy.price_per_tib_usd

        billable_tib = max(0.0, tib_processed - self.policy.monthly_free_tib) if apply_free_tier else tib_processed
        billable_cost = billable_tib * self.policy.price_per_tib_usd

        cost_estimate = {
            "bytes_processed": bytes_processed,
            "tib_processed": round(tib_processed, 6),
            "billing_unit": self.policy.billing_unit,
            "price_per_tib_usd": self.policy.price_per_tib_usd,
            "estimated_gross_cost_usd": round(gross_cost, 4),
            "free_tier_applied": apply_free_tier,
            "estimated_billable_cost_usd": round(billable_cost, 4),
            "price_source": "configured_policy",
            "cost_disclaimer": "Estimate based on on-demand list pricing. Actual billing depends on reservations, region, discounts, and free tier.",
        }

        # Step 4: Decision Engine
        decision = "ALLOW"
        if not contract_compliant:
            decision = "REQUIRE_REVIEW"

        # Byte budget check
        if self.policy.maximum_bytes_billed and bytes_processed > self.policy.maximum_bytes_billed:
            decision = "DENY"
            bq_error = f"Byte budget exceeded: query estimates {bytes_processed} bytes, limit is {self.policy.maximum_bytes_billed} bytes."
            execution_mode = "budget_exceeded"

        if execution_mode in ("parse_failed", "dry_run_failed"):
            decision = "DENY"

        return {
            "engine": "bigquery",
            "execution_mode": execution_mode,
            "sql_hash": sql_hash,
            "contract_id": metric_def.metric,
            "query_length_chars": len(sql),
            "dialect": dialect,
            "bytes_processed": bytes_processed,
            "cost_estimate": cost_estimate,
            "contract_compliant": contract_compliant,
            "violations": violations,
            "bq_error": bq_error,
            "decision": decision,
            "local_ast_latency_ms": round(ast_latency_ms, 2),
            "dry_run_api_latency_ms": round(api_latency_ms, 2),
        }
