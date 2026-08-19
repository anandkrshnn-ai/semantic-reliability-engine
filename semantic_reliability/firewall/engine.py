import uuid
import time
import json
import logging
import sqlglot
from pathlib import Path
from typing import Dict, Tuple, Optional, List
import yaml

from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants
from semantic_reliability.compiler.contracts import SemanticContractValidator, ContractViolation
from .models import EvaluateRequest, EvaluateResponse, Violation, Decision, RiskLevel
from .policy import PolicyEngine

logger = logging.getLogger("sre.firewall")


class ContractRegistry:
    """In-memory registry of declarative metric contracts."""

    def __init__(self, contract_dir: Optional[str | Path] = None):
        self.contracts: Dict[str, Tuple[MetricDefinition, str]] = {}
        if contract_dir and Path(contract_dir).exists():
            self._load_contracts(contract_dir)

    def _load_contracts(self, contract_dir: str | Path):
        for path in Path(contract_dir).glob("**/*.yaml"):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "metric" in data:
                    version = data.get("version", "1.0.0")
                    definition = MetricDefinition(**data)
                    self.contracts[definition.metric] = (definition, version)
            except Exception as e:
                logger.warning(f"Skipping unparseable contract {path}: {str(e)}")

    def register(self, metric_def: MetricDefinition, version: str = "1.0.0"):
        self.contracts[metric_def.metric] = (metric_def, version)

    def get(self, metric_id: str) -> Tuple[MetricDefinition, str]:
        if metric_id not in self.contracts:
            raise ValueError(f"Unknown metric contract: '{metric_id}'. Registered metrics: {list(self.contracts.keys())}")
        return self.contracts[metric_id]


class SemanticEvaluator:
    """Evaluates agentic SQL queries against policy-backed metric contracts and generates audit trails."""

    def __init__(self, registry: ContractRegistry, policy: Optional[PolicyEngine] = None):
        self.registry = registry
        self.policy = policy or PolicyEngine(strict_mode=True)
        self.audit_log: List[Dict[str, Any]] = []

    def evaluate(self, req: EvaluateRequest) -> EvaluateResponse:
        trace_id = f"sre-{uuid.uuid4()}"

        try:
            definition, version = self.registry.get(req.metric_id)
            sqlglot.parse_one(req.sql, read=req.dialect)
        except ValueError as ve:
            return EvaluateResponse(
                request_id=req.request_id,
                trace_id=trace_id,
                decision=Decision.DENY,
                execution_allowed=False,
                contract_compliant=False,
                risk=RiskLevel.CRITICAL,
                violations=[],
                contract_version="N/A",
                message=str(ve),
            )
        except Exception as e:
            # Unparseable SQL is an automatic DENY
            return EvaluateResponse(
                request_id=req.request_id,
                trace_id=trace_id,
                decision=Decision.DENY,
                execution_allowed=False,
                contract_compliant=False,
                risk=RiskLevel.CRITICAL,
                violations=[],
                contract_version="N/A",
                message=f"SQL Parse Error: {str(e)}",
            )

        # Run Contract Validator
        c_res = SemanticContractValidator.validate(req.sql, definition, dialect=req.dialect)
        
        violations: List[Violation] = []
        for v in c_res.violations:
            violations.append(Violation(
                rule=v.invariant_rule,
                expected=f"Satisfy {v.invariant_category} contract",
                found=v.details,
                severity="ERROR",
                invariant_type=v.invariant_category,
            ))

        decision, risk, message = self.policy.evaluate(violations)
        execution_allowed = decision in (Decision.ALLOW, Decision.AUDIT)
        contract_compliant = (len(violations) == 0)

        # Record immutable audit trace
        self._record_audit_trace(trace_id, req, decision, violations, version)

        return EvaluateResponse(
            request_id=req.request_id,
            trace_id=trace_id,
            decision=decision,
            execution_allowed=execution_allowed,
            contract_compliant=contract_compliant,
            risk=risk,
            violations=violations,
            contract_version=version,
            message=message,
        )

    def _record_audit_trace(self, trace_id: str, req: EvaluateRequest, decision: Decision, violations: List[Violation], version: str):
        trace = {
            "trace_id": trace_id,
            "timestamp": time.time(),
            "agent_id": req.agent_id,
            "metric_id": req.metric_id,
            "contract_version": version,
            "sql_hash": hash(req.sql),
            "decision": decision.value,
            "violation_count": len(violations),
            "violations": [v.model_dump() for v in violations],
        }
        self.audit_log.append(trace)
        logger.info(json.dumps(trace))
