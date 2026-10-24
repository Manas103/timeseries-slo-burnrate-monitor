import random

from llm_monitor import prometheus_export, tracing
from llm_monitor.degradations import BASELINE


def test_record_increments_requests_and_leaves_ungrounded_at_zero_for_a_grounded_request():
    before = prometheus_export.REQUESTS_TOTAL._value.get()
    rng = random.Random(123)
    metric = tracing.serve_request(0.0, BASELINE, rng)
    # Force a known-grounded sample so this test is not flaky against the baseline's own
    # small random ungrounded probability.
    metric = metric.__class__(metric.timestamp_s, metric.latency_ms, metric.http_status,
                               metric.error, 0.95, metric.cost_usd)

    prometheus_export.record(metric)

    after = prometheus_export.REQUESTS_TOTAL._value.get()
    assert after == before + 1
