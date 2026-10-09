from burnrate import Run, evaluate


def clean_run(i):
    return Run(str(i), "NONE", 0.0, 2.0)


def test_clean_history_never_pages():
    runs = [clean_run(i) for i in range(20)]
    assert evaluate(runs) == set()


def test_a_severe_error_rate_blowout_pages():
    bad = Run("bad", "ERROR_RATE", 40.0, 2.0)
    assert "bad" in evaluate([bad])


def test_a_mild_latency_blip_does_not_page():
    mild = Run("mild", "LATENCY", 0.0, 5.0)
    assert "mild" not in evaluate([mild])


def test_a_severe_latency_spike_pages():
    bad = Run("bad-latency", "LATENCY", 0.0, 400.0)
    assert "bad-latency" in evaluate([bad])
