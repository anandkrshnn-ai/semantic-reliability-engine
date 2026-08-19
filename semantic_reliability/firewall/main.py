import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from starlette.responses import Response

from .models import EvaluateRequest, EvaluateResponse
from .engine import SemanticEvaluator, ContractRegistry
from .policy import PolicyEngine

# Try importing prometheus_client, or fallback gracefully if not installed in current environment
try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
    REQUESTS = Counter('sre_requests_total', 'Total requests to firewall', ['agent_id'])
    DECISIONS = Counter('sre_decisions_total', 'Decisions made', ['decision'])
    VIOLATIONS = Counter('sre_contract_violations_total', 'Violations caught', ['rule'])
    LATENCY = Histogram('sre_evaluation_latency_seconds', 'Time to evaluate contract')
    BLOCKED = Counter('sre_execution_blocked_total', 'Queries blocked')
except ImportError:
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain"

app = FastAPI(
    title="SRE Semantic Firewall",
    description="Runtime policy engine and audit control plane for AI-generated analytical SQL.",
    version="8.1.0"
)

# Auto-discover benchmark corpus contracts or examples
DEFAULT_CONTRACTS_DIR = Path(__file__).resolve().parent.parent.parent / "benchmark_corpus"
registry = ContractRegistry(contract_dir=DEFAULT_CONTRACTS_DIR)
policy = PolicyEngine(strict_mode=True)
evaluator = SemanticEvaluator(registry, policy)


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_sql(req: EvaluateRequest):
    if PROMETHEUS_AVAILABLE:
        REQUESTS.labels(agent_id=req.agent_id).inc()

    start = time.perf_counter()
    response = evaluator.evaluate(req)
    duration = time.perf_counter() - start

    if PROMETHEUS_AVAILABLE:
        LATENCY.observe(duration)
        DECISIONS.labels(decision=response.decision.value).inc()
        for v in response.violations:
            VIOLATIONS.labels(rule=v.rule).inc()
        if not response.execution_allowed:
            BLOCKED.inc()

    return response


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "contracts_loaded": len(registry.contracts),
        "metrics": list(registry.contracts.keys())
    }


@app.get("/metrics")
async def metrics():
    if PROMETHEUS_AVAILABLE:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    return Response(content="# Prometheus metrics unavailable (install prometheus_client)\n", media_type=CONTENT_TYPE_LATEST)
