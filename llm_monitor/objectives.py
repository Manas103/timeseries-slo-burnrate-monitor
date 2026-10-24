"""Written SLO objectives for the LLM request path, provisioned alongside the monitoring
stack (see terraform/). Each objective pairs a budget with the metric it bounds; burnrate_window.py
turns an observed value into a multiple of that budget ("burn rate"), the same value/budget
convention python/burnrate.py already uses for latency and saturation.

Groundedness and cost per request are the two objectives this extension adds; p99 latency is
carried over from the sibling's own budget convention (not its exact number, since this is a
different service).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Objective:
    name: str
    unit: str
    budget: float
    description: str


# A request counts as "ungrounded" (a bad event, the same framing as an error-rate SLO) when
# its groundedness score falls below this threshold.
GROUNDEDNESS_THRESHOLD = 0.70

# At most 3% of requests may be ungrounded; this is the error budget the burn-rate evaluator
# measures against, not the groundedness score itself.
GROUNDEDNESS_OBJECTIVE = Objective(
    name="groundedness",
    unit="fraction ungrounded",
    budget=0.03,
    description="at most 3% of requests may score below the groundedness threshold",
)

LATENCY_P99_OBJECTIVE = Objective(
    name="latency_p99_ms",
    unit="ms",
    budget=800.0,
    description="p99 end-to-end latency (retrieval + model call + post-processing) at most 800ms",
)

COST_OBJECTIVE = Objective(
    name="cost_per_request_usd",
    unit="usd",
    budget=0.02,
    description="mean cost per request at most $0.02",
)

ALL_OBJECTIVES = (GROUNDEDNESS_OBJECTIVE, LATENCY_P99_OBJECTIVE, COST_OBJECTIVE)
