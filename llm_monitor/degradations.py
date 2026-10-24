"""The baseline profile and the 20 injected silent-degradation scenarios. Each profile is a
plausible, named cause of an LLM-backed service quietly answering worse while HTTP status, error
rate, and latency all stay inside budget, which is exactly what the resume claim and the
sibling's own disclosed limitation (Honest framing) are both about: an incident with nothing
wrong on the infrastructure dashboards.

Severity (ungrounded_rate, the probability a given request scores below
objectives.GROUNDEDNESS_THRESHOLD) is assigned once here, by design, not searched for after
simulating; two scenarios are deliberately mild enough that the burn-rate evaluator's windows
never cross even the slow tier's threshold, the disclosed miss this project reports rather than
hides.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    ungrounded_rate: float
    description: str

    def groundedness(self, rng):
        if rng.random() < self.ungrounded_rate:
            return rng.uniform(0.10, 0.65)
        return rng.uniform(0.75, 0.99)

    def retrieval_latency_ms(self, rng):
        return rng.uniform(40.0, 90.0)

    def model_latency_ms(self, rng):
        return rng.uniform(150.0, 300.0)

    def post_processing_latency_ms(self, rng):
        return rng.uniform(10.0, 40.0)

    def cost_usd(self, rng):
        return rng.uniform(0.004, 0.009)


BASELINE = Profile("baseline", ungrounded_rate=0.015, description="healthy service")

_DEGRADATION_SPECS = [
    (0.95, "retrieval index rolled back to a stale snapshot, serving outdated passages"),
    (0.91, "reranker model silently downgraded to a weaker checkpoint on deploy"),
    (0.87, "retrieval top-k reduced from 5 to 1 by a misapplied config default"),
    (0.83, "model provider A/B-tested a cheaper model into 100% of traffic without a flag flip here"),
    (0.80, "prompt template regression dropped the system instruction block"),
    (0.76, "context window truncation silently drops the retrieved passage before the model call"),
    (0.72, "vector store reindex left half the corpus temporarily missing"),
    (0.68, "quantized model variant pinned in a rollback, trading fidelity for latency"),
    (0.64, "temperature parameter accidentally raised, increasing hallucination rate"),
    (0.60, "embedding model version mismatch between the index and the query path"),
    (0.57, "post-processing regex over-aggressively strips grounding citations"),
    (0.53, "cache layer serves a stale answer for a semantically new question"),
    (0.49, "fallback path silently engaged on primary-model timeout, answering ungrounded"),
    (0.45, "summarization step drops a key entity before the citation check"),
    (0.40, "safety filter over-triggers and returns a hedge/non-answer scored as ungrounded"),
    (0.35, "translation layer subtly alters factual content for non-English requests"),
    (0.30, "feature flag flipped an experimental prompt variant to full traffic"),
    (0.25, "rate-limit fallback serves a cached generic answer under load"),
    (0.08, "a minor retrieval ranking regression slightly favors a weaker passage"),
    (0.05, "a single reranker feature was dropped in a refactor, a small, genuinely subtle regression"),
]

DEGRADATIONS = [
    Profile(name=f"DEG-{i + 1:02d}", ungrounded_rate=rate, description=description)
    for i, (rate, description) in enumerate(_DEGRADATION_SPECS)
]

assert len(DEGRADATIONS) == 20
