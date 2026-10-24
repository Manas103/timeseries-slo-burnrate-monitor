from llm_monitor.degradations import BASELINE, DEGRADATIONS
from llm_monitor.objectives import GROUNDEDNESS_OBJECTIVE


def test_exactly_twenty_degradation_scenarios():
    assert len(DEGRADATIONS) == 20
    names = {d.name for d in DEGRADATIONS}
    assert len(names) == 20


def test_baseline_ungrounded_rate_is_inside_the_error_budget():
    assert BASELINE.ungrounded_rate < GROUNDEDNESS_OBJECTIVE.budget


def test_every_degradation_is_worse_than_baseline():
    for d in DEGRADATIONS:
        assert d.ungrounded_rate > BASELINE.ungrounded_rate
