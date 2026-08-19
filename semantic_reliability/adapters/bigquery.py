"""BigQuery Dry-Run Adapter for semantic validation and cost estimation."""
from typing import Optional, Dict, Any, List
import sqlglot

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.compiler.contracts import SemanticContractValidator


class BigQueryDryRunAdapter:
    """Validates SQL against BigQuery dry-run API and SRE Semantic Contracts without data scanning."""

    COST_PER_TB_USD: float = 5.0  # Standard GCP on-demand analysis pricing ($5/TB)

    def __init__(self, project_id: Optional[str] = None, credentials=None, client=None):
        self.project_id = project_id
        self.credentials = credentials
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from google.cloud import bigquery
            self._client = bigquery.Client(project=self.project_id, credentials=self.credentials)
            return self._client
        except Exception as e:
            return None

    def evaluate(
        self,
        sql: str,
        metric_def: MetricDefinition,
        dialect: str = "bigquery",
        mock_bytes_processed: Optional[int] = None,
    ) -> Dict[str, Any]:
        # 1. Parse & Contract Validation
        try:
            sqlglot.parse_one(sql, read=dialect)
            eval_res = SemanticContractValidator.validate(candidate_sql=sql, metric_def=metric_def, dialect=dialect)
            violations = [f"{v.invariant_category}: {v.invariant_rule}" for v in eval_res.violations]
            contract_compliant = eval_res.passed
        except Exception as e:
            return {
                "engine": "bigquery",
                "execution_mode": "parse_failed",
                "bytes_processed": 0,
                "estimated_cost": 0.0,
                "contract_compliant": False,
                "violations": [],
                "bq_error": f"SQLGlot parse error: {str(e)}",
                "decision": "DENY",
            }

        # 2. BigQuery Dry-Run (Cost & Syntax Validation)
        bytes_processed = 0
        execution_mode = "dry_run"
        bq_error = None

        if mock_bytes_processed is not None:
            bytes_processed = mock_bytes_processed
        else:
            client = self._get_client()
            if client is not None:
                try:
                    from google.cloud import bigquery
                    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
                    query_job = client.query(sql, job_config=job_config)
                    bytes_processed = query_job.total_bytes_processed or 0
                except Exception as e:
                    execution_mode = "dry_run_failed"
                    bq_error = str(e)
            else:
                # BigQuery client unavailable (offline / mock estimation)
                execution_mode = "dry_run_simulated"
                # Heuristic estimation: ~10MB baseline for dry run
                bytes_processed = 10 * 1024 * 1024

        estimated_cost = (bytes_processed / (1024 ** 4)) * self.COST_PER_TB_USD

        # 3. Decision Engine
        decision = "ALLOW"
        if not contract_compliant:
            decision = "REQUIRE_REVIEW"
        if execution_mode in ("parse_failed", "dry_run_failed"):
            decision = "DENY"

        return {
            "engine": "bigquery",
            "execution_mode": execution_mode,
            "bytes_processed": bytes_processed,
            "estimated_cost": round(estimated_cost, 6),
            "contract_compliant": contract_compliant,
            "violations": violations,
            "bq_error": bq_error,
            "decision": decision,
        }
