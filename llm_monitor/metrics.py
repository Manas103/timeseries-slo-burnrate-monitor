"""The per-request record the rest of this extension operates on. One RequestMetrics is
produced per simulated request by tracing.serve_request(); the burn-rate evaluator never sees
anything else."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestMetrics:
    timestamp_s: float
    latency_ms: float
    http_status: int
    error: bool
    groundedness: float
    cost_usd: float
