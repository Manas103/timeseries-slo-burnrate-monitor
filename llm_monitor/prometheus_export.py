"""Real Prometheus exposition for the counters/histograms terraform/main.tf's alerting rules
query: llm_monitor_requests_total, llm_monitor_ungrounded_requests_total,
llm_monitor_latency_ms (a Histogram, for the p99 rule), and llm_monitor_cost_usd (a Summary, for
the per-request cost rule). start_http_server here is real; it is used for the live demo in
"Building and running," not for the measured 18-of-20 benchmark, which runs the evaluator
directly against generated RequestMetrics (see Honest framing).
"""
from prometheus_client import Counter, Histogram, Summary, start_http_server

from .objectives import GROUNDEDNESS_THRESHOLD

REQUESTS_TOTAL = Counter("llm_monitor_requests_total", "Total requests served")
UNGROUNDED_TOTAL = Counter("llm_monitor_ungrounded_requests_total", "Requests scored below the groundedness threshold")
LATENCY_MS = Histogram("llm_monitor_latency_ms", "End-to-end request latency in milliseconds",
                        buckets=(50, 100, 200, 400, 600, 800, 1000, 1500, 2000))
COST_USD = Summary("llm_monitor_cost_usd", "Cost per request in USD")


def record(metric) -> None:
    REQUESTS_TOTAL.inc()
    if metric.groundedness < GROUNDEDNESS_THRESHOLD:
        UNGROUNDED_TOTAL.inc()
    LATENCY_MS.observe(metric.latency_ms)
    COST_USD.observe(metric.cost_usd)


def serve_metrics(port: int = 9108) -> None:
    start_http_server(port)
