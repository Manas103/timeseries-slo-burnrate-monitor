"""Multi-window multi-burn-rate SLO alerting over a real, continuous per-request time series,
following the same Google SRE Workbook tiers python/burnrate.py uses, but able to implement the
literal two-window design that sibling repo's README disclosed it could not: a real short window
AND a real long window (12x longer), independently measured from one continuous metric stream,
because this extension's simulated requests carry real timestamps a discrete one-measurement-
per-run dataset does not have.

Window sizes are scaled to a lookback period of minutes/hours rather than the Workbook's example
28-day budget window, because a silent LLM-quality incident needs catching in minutes, not days;
this is a deliberate, disclosed choice of lookback period, not a deviation from the rule itself
(the Workbook's own guidance is to choose window sizes against your own error-budget lookback).
"""
from collections import deque
from dataclasses import dataclass

from .objectives import COST_OBJECTIVE, GROUNDEDNESS_OBJECTIVE, GROUNDEDNESS_THRESHOLD, LATENCY_P99_OBJECTIVE

# (long_window_seconds, short_window_seconds, burn_threshold), both ratios drawn from the real
# SRE Workbook tiers (12x window ratio, 14.4x fast / 6.0x slow threshold).
FAST_TIER = (10 * 60.0, 50.0, 14.4)
SLOW_TIER = (60 * 60.0, 5 * 60.0, 6.0)
TIERS = (FAST_TIER, SLOW_TIER)


def burn_rate(value: float, budget: float) -> float:
    if budget == 0:
        return 0.0
    return value / budget


def naive_window_slice(metrics, t, window_s):
    """Deliberately slow, obviously correct: filters the full list every call. This is the
    reference oracle SlidingGroundednessWindow is diffed against in tests."""
    return [m for m in metrics if t - window_s < m.timestamp_s <= t]


def naive_fraction_ungrounded(metrics, t, window_s):
    window = naive_window_slice(metrics, t, window_s)
    if not window:
        return 0.0, 0
    ungrounded = sum(1 for m in window if m.groundedness < GROUNDEDNESS_THRESHOLD)
    return ungrounded / len(window), len(window)


def naive_p99_latency(metrics, t, window_s):
    window = naive_window_slice(metrics, t, window_s)
    if not window:
        return 0.0
    latencies = sorted(m.latency_ms for m in window)
    idx = min(len(latencies) - 1, int(0.99 * len(latencies)))
    return latencies[idx]


def naive_mean_cost(metrics, t, window_s):
    window = naive_window_slice(metrics, t, window_s)
    if not window:
        return 0.0
    return sum(m.cost_usd for m in window) / len(window)


@dataclass
class _Sample:
    timestamp_s: float
    ungrounded: bool


class SlidingGroundednessWindow:
    """The fast path: an O(1)-amortized-per-arrival sliding window over a fixed duration,
    maintained incrementally as samples arrive in non-decreasing timestamp order, rather than
    re-filtering the whole history on every query like naive_fraction_ungrounded does."""

    def __init__(self, window_s: float):
        self.window_s = window_s
        self._buffer: deque = deque()
        self._ungrounded_count = 0

    def advance(self, sample: _Sample) -> None:
        self._buffer.append(sample)
        if sample.ungrounded:
            self._ungrounded_count += 1
        cutoff = sample.timestamp_s - self.window_s
        while self._buffer and self._buffer[0].timestamp_s <= cutoff:
            evicted = self._buffer.popleft()
            if evicted.ungrounded:
                self._ungrounded_count -= 1

    def fraction_ungrounded(self):
        if not self._buffer:
            return 0.0, 0
        return self._ungrounded_count / len(self._buffer), len(self._buffer)


class BurnRateEvaluator:
    """Drives SlidingGroundednessWindow incrementally over an ordered stream of RequestMetrics
    and decides, at each arrival, whether the multi-window multi-burn-rate rule pages."""

    def __init__(self):
        self._windows = {window_s: SlidingGroundednessWindow(window_s)
                          for tier in TIERS for window_s in (tier[0], tier[1])}
        self._history = []

    def observe(self, metric):
        self._history.append(metric)
        sample = _Sample(metric.timestamp_s, metric.groundedness < GROUNDEDNESS_THRESHOLD)
        for window in self._windows.values():
            window.advance(sample)
        return self.pages()

    def pages(self):
        for long_s, short_s, threshold in TIERS:
            long_frac, long_n = self._windows[long_s].fraction_ungrounded()
            short_frac, short_n = self._windows[short_s].fraction_ungrounded()
            if long_n == 0 or short_n == 0:
                continue
            long_burn = burn_rate(long_frac, GROUNDEDNESS_OBJECTIVE.budget)
            short_burn = burn_rate(short_frac, GROUNDEDNESS_OBJECTIVE.budget)
            if long_burn >= threshold and short_burn >= threshold:
                return True
        return False

    def latency_and_cost_within_budget(self, t):
        p99 = naive_p99_latency(self._history, t, SLOW_TIER[0])
        mean_cost = naive_mean_cost(self._history, t, SLOW_TIER[0])
        latency_ok = burn_rate(p99, LATENCY_P99_OBJECTIVE.budget) < 1.0
        cost_ok = burn_rate(mean_cost, COST_OBJECTIVE.budget) < 1.0
        return latency_ok, cost_ok
