import random

from llm_monitor import tracing
from llm_monitor.burnrate_window import (
    FAST_TIER, SLOW_TIER, BurnRateEvaluator, naive_fraction_ungrounded,
)
from llm_monitor.degradations import BASELINE, DEGRADATIONS


def _generate_stream(seed, n, interval_s=10.0, profile=BASELINE):
    rng = random.Random(seed)
    metrics = []
    t = 0.0
    for _ in range(n):
        metrics.append(tracing.serve_request(t, profile, rng))
        t += interval_s
    return metrics


def _generate_continuous_stream(seed, segments, interval_s=10.0):
    """One continuously advancing timestamp across a sequence of (profile, count) segments,
    the same way simulate.py never resets its clock when a profile changes."""
    rng = random.Random(seed)
    metrics = []
    t = 0.0
    for profile, count in segments:
        for _ in range(count):
            metrics.append(tracing.serve_request(t, profile, rng))
            t += interval_s
    return metrics


def test_sliding_window_matches_the_naive_reference_oracle_exactly():
    """Diffs the fast, incremental SlidingGroundednessWindow against the deliberately slow
    naive_fraction_ungrounded reference, sampled at every tenth arrival across a mixed clean
    and degraded stream, including a window boundary that is easy to get off by one."""
    metrics = _generate_continuous_stream(1, [(BASELINE, 400), (DEGRADATIONS[0], 400)])

    evaluator = BurnRateEvaluator()
    checked = 0
    for i, metric in enumerate(metrics):
        evaluator.observe(metric)
        if i % 10 != 0:
            continue
        for window_s in (FAST_TIER[0], FAST_TIER[1], SLOW_TIER[0], SLOW_TIER[1]):
            fast_frac, fast_n = evaluator._windows[window_s].fraction_ungrounded()
            naive_frac, naive_n = naive_fraction_ungrounded(metrics[: i + 1], metric.timestamp_s, window_s)
            assert fast_n == naive_n, f"count mismatch at i={i}, window={window_s}"
            assert abs(fast_frac - naive_frac) < 1e-12, f"fraction mismatch at i={i}, window={window_s}"
            checked += 1
    assert checked > 100


def test_clean_baseline_stream_never_pages():
    metrics = _generate_stream(42, 500, profile=BASELINE)
    evaluator = BurnRateEvaluator()
    paged = any(evaluator.observe(m) for m in metrics)
    assert not paged


def test_a_severe_degradation_eventually_pages():
    metrics = _generate_continuous_stream(7, [(BASELINE, 500), (DEGRADATIONS[0], 200)])
    evaluator = BurnRateEvaluator()
    paged = any(evaluator.observe(m) for m in metrics)
    assert paged


def test_a_mild_degradation_never_pages():
    mild = DEGRADATIONS[-1]
    metrics = _generate_continuous_stream(9, [(BASELINE, 500), (mild, 500)])
    evaluator = BurnRateEvaluator()
    paged = any(evaluator.observe(m) for m in metrics)
    assert not paged
