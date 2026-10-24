"""Orchestrates the two measurements this extension's resume bullet depends on:

1. A 40-simulated-hour clean run (one request every REQUEST_INTERVAL_S), counting false pages.
2. Each of the 20 degradation scenarios, run after a 2-hour clean warm-up (so the sliding
   windows are not empty at onset) for a 2-hour active window, recording whether the
   multi-window burn-rate rule paged and, if so, how many minutes after onset.

Request timestamps are real simulated wall-clock seconds (not real sleep time); tracing.py's
spans are still real OpenTelemetry spans per request, see its own Honest framing note.
"""
import random

from . import tracing
from .burnrate_window import BurnRateEvaluator
from .degradations import BASELINE, DEGRADATIONS

REQUEST_INTERVAL_S = 10.0
WARMUP_S = 2 * 60 * 60.0
ACTIVE_S = 2 * 60 * 60.0
CLEAN_HOURS = 40
CLEAN_DURATION_S = CLEAN_HOURS * 60 * 60.0

SEED = 20261024


def run_clean_simulation(seed=SEED):
    rng = random.Random(seed)
    evaluator = BurnRateEvaluator()
    t = 0.0
    false_pages = 0
    requests = 0
    while t < CLEAN_DURATION_S:
        metric = tracing.serve_request(t, BASELINE, rng)
        paged = evaluator.observe(metric)
        requests += 1
        if paged:
            false_pages += 1
        t += REQUEST_INTERVAL_S
    return {"requests": requests, "false_pages": false_pages, "hours": CLEAN_HOURS}


def run_degradation_scenario(profile, seed):
    rng = random.Random(seed)
    evaluator = BurnRateEvaluator()
    t = 0.0

    while t < WARMUP_S:
        metric = tracing.serve_request(t, BASELINE, rng)
        evaluator.observe(metric)
        t += REQUEST_INTERVAL_S

    onset = t
    detected_at = None
    while t < onset + ACTIVE_S:
        metric = tracing.serve_request(t, profile, rng)
        paged = evaluator.observe(metric)
        if paged and detected_at is None:
            detected_at = t
        t += REQUEST_INTERVAL_S

    latency_ok, cost_ok = evaluator.latency_and_cost_within_budget(t - REQUEST_INTERVAL_S)

    result = {
        "scenario": profile.name,
        "description": profile.description,
        "ungrounded_rate": profile.ungrounded_rate,
        "caught": detected_at is not None,
        "detection_latency_s": (detected_at - onset) if detected_at is not None else None,
        "latency_within_budget": latency_ok,
        "cost_within_budget": cost_ok,
    }
    return result


def run_all_degradation_scenarios(seed=SEED):
    results = [run_degradation_scenario(profile, seed + i) for i, profile in enumerate(DEGRADATIONS)]
    caught = [r for r in results if r["caught"]]
    missed = [r for r in results if not r["caught"]]
    detection_minutes = sorted(r["detection_latency_s"] / 60.0 for r in caught)
    median_minutes = (
        detection_minutes[len(detection_minutes) // 2]
        if len(detection_minutes) % 2 == 1
        else (detection_minutes[len(detection_minutes) // 2 - 1] + detection_minutes[len(detection_minutes) // 2]) / 2
        if detection_minutes else None
    )
    return {
        "total": len(results),
        "caught": len(caught),
        "missed": len(missed),
        "median_detection_minutes": median_minutes,
        "all_latency_within_budget": all(r["latency_within_budget"] for r in results),
        "all_cost_within_budget": all(r["cost_within_budget"] for r in results),
        "results": results,
    }


def main():
    import json
    clean = run_clean_simulation()
    degradation = run_all_degradation_scenarios()
    output = {"clean": clean, "degradation": degradation}
    print(json.dumps(output, indent=2))
    return output


if __name__ == "__main__":
    main()
