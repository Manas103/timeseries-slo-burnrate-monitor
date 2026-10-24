"""Prints 2 real requests' worth of OpenTelemetry spans to the console, one healthy and one
degraded, as the evidence that retrieval/model_call/post_processing are real child spans under
one parent per request. Not part of the measured benchmark; see simulate.py for that.
"""
import random

from opentelemetry.sdk.trace.export import ConsoleSpanExporter

from . import tracing
from .degradations import BASELINE, DEGRADATIONS


def main():
    tracing.add_span_exporter(ConsoleSpanExporter())
    rng = random.Random(1)
    print("--- healthy request ---")
    tracing.serve_request(0.0, BASELINE, rng)
    print("--- degraded request (DEG-01) ---")
    tracing.serve_request(10.0, DEGRADATIONS[0], rng)


if __name__ == "__main__":
    main()
