import random

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from llm_monitor import tracing
from llm_monitor.degradations import BASELINE


def test_serve_request_produces_a_parent_span_and_three_named_child_spans():
    exporter = InMemorySpanExporter()
    tracing.add_span_exporter(exporter)
    exporter.clear()

    tracing.serve_request(0.0, BASELINE, random.Random(1))

    spans = exporter.get_finished_spans()
    names = sorted(s.name for s in spans)
    assert names == ["model_call", "post_processing", "retrieval", "serve_request"]

    parent = next(s for s in spans if s.name == "serve_request")
    children = [s for s in spans if s.name != "serve_request"]
    for child in children:
        assert child.parent is not None
        assert child.parent.span_id == parent.context.span_id


def test_serve_request_returns_metrics_consistent_with_the_spans():
    exporter = InMemorySpanExporter()
    tracing.add_span_exporter(exporter)
    exporter.clear()

    metric = tracing.serve_request(123.0, BASELINE, random.Random(2))

    assert metric.timestamp_s == 123.0
    assert metric.http_status == 200
    assert metric.error is False
    assert metric.latency_ms > 0
    assert 0.0 <= metric.groundedness <= 1.0
    assert metric.cost_usd > 0
