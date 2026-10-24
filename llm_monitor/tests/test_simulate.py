"""Runs the real simulation at reduced scale (fewer clean hours, fewer degradation scenarios)
so the test suite stays fast; the full-scale numbers these mirror are measured once by
llm_monitor/simulate.py and recorded in docs/llm_monitor_simulation_output.json."""
from llm_monitor import simulate


def test_a_short_clean_run_pages_zero_times():
    old_duration = simulate.CLEAN_DURATION_S
    try:
        simulate.CLEAN_DURATION_S = 2 * 60 * 60.0
        result = simulate.run_clean_simulation(seed=1)
        assert result["false_pages"] == 0
        assert result["requests"] > 0
    finally:
        simulate.CLEAN_DURATION_S = old_duration


def test_degradation_scenario_result_shape():
    from llm_monitor.degradations import DEGRADATIONS
    result = simulate.run_degradation_scenario(DEGRADATIONS[0], seed=5)
    assert result["scenario"] == DEGRADATIONS[0].name
    assert result["caught"] is True
    assert result["detection_latency_s"] > 0
    assert result["latency_within_budget"] is True
    assert result["cost_within_budget"] is True


def test_a_mild_scenario_is_honestly_reported_as_missed():
    from llm_monitor.degradations import DEGRADATIONS
    mildest = DEGRADATIONS[-1]
    result = simulate.run_degradation_scenario(mildest, seed=6)
    assert result["caught"] is False
    assert result["detection_latency_s"] is None
