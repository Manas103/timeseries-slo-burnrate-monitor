"""Real OpenTelemetry instrumentation of the LLM request path: one parent span per request,
with three child spans, retrieval, model_call, and post_processing, matching the resume claim
exactly. The SDK, the TracerProvider, and the span tree are real; only the durations recorded on
each span are simulated values rather than the span's own wall-clock elapsed time, because
generating the tens of thousands of requests the clean-hours simulation needs at real sleep-based
latencies would take hours to run. See the README's Honest framing for this disclosure.
"""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SimpleSpanProcessor

from .metrics import RequestMetrics

_provider = TracerProvider()
trace.set_tracer_provider(_provider)
_tracer = trace.get_tracer("llm_monitor")


def add_span_exporter(exporter: SpanExporter) -> None:
    _provider.add_span_processor(SimpleSpanProcessor(exporter))


def serve_request(timestamp_s: float, profile, rng) -> RequestMetrics:
    """Simulates one request through retrieval, model_call, and post_processing, each its own
    real OpenTelemetry span under one parent span, and returns the resulting RequestMetrics."""
    with _tracer.start_as_current_span("serve_request") as parent:
        parent.set_attribute("timestamp_s", timestamp_s)

        with _tracer.start_as_current_span("retrieval") as span:
            retrieval_ms = profile.retrieval_latency_ms(rng)
            span.set_attribute("phase", "retrieval")
            span.set_attribute("duration_ms", retrieval_ms)

        with _tracer.start_as_current_span("model_call") as span:
            model_ms = profile.model_latency_ms(rng)
            span.set_attribute("phase", "model_call")
            span.set_attribute("duration_ms", model_ms)

        with _tracer.start_as_current_span("post_processing") as span:
            post_ms = profile.post_processing_latency_ms(rng)
            groundedness = profile.groundedness(rng)
            span.set_attribute("phase", "post_processing")
            span.set_attribute("duration_ms", post_ms)
            span.set_attribute("groundedness", groundedness)

        total_latency_ms = retrieval_ms + model_ms + post_ms
        cost_usd = profile.cost_usd(rng)
        parent.set_attribute("latency_ms", total_latency_ms)
        parent.set_attribute("cost_usd", cost_usd)
        parent.set_attribute("groundedness", groundedness)

    return RequestMetrics(
        timestamp_s=timestamp_s,
        latency_ms=total_latency_ms,
        http_status=200,
        error=False,
        groundedness=groundedness,
        cost_usd=cost_usd,
    )
