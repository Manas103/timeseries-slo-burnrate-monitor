# Time-Series Monitoring Service with Multi-Burn-Rate SLO Alerting

A from-scratch time-series compression codec in C++ (delta-of-delta timestamps, XOR float compression, Gorilla-style) and a Python multi-burn-rate SLO alert evaluator following Google's SRE Workbook tiers, extending `release-health-gate-service-metrics` by reusing its seeded ground truth (40 one-class regressions, 60 clean releases) rather than rebuilding it. Every number below was measured by actually running this code, not targeted in advance.

## Relationship to the sibling repo

This project does not duplicate `release-health-gate-service-metrics`'s canary service, load-replay harness, or its own READS gate; it reads that repo's already-measured `docs/regression_matrix.csv` and `docs/clean_build_matrix.csv` directly and adds the two things the design called for that the sibling lacks: a real time-series ingest/compression engine in C++, and a burn-rate evaluator implementing the SRE Workbook's tiers rather than a static per-service budget. See `https://github.com/Manas103/release-health-gate-service-metrics`.

## Honest framing, up front

- **This is a codec and an alert-evaluation rule, not a running ingest service.** There is no storage engine, no query language, no running server; `src/codec.cpp` is a self-check-and-benchmark binary, and `python/burnrate.py` is a batch evaluator over the sibling's CSVs.
- **The two-window burn-rate test could not be implemented as the SRE Workbook describes it, and that is disclosed rather than hidden.** The Workbook pairs a short window with a long window roughly 12x its duration from one continuous metric stream. The sibling's ground truth is one discrete measurement per run with no sub-run time dimension, so there is no real second window to build; see Findings for what happened when this was first attempted literally. The evaluator here instead applies the Workbook's two burn-rate thresholds as two severity tiers on the one measurement each run has.
- **Machine and toolchain.** Windows 11 Home, WSL2 Ubuntu 22.04, g++ 11.4 (`-O2 -std=c++17`), Python 3.10, pytest 6.2.5. No sanitizers were run for this project (time-boxed scope; see Limitations).

## Architecture

```
src/codec.cpp              TimestampEncoder (delta-of-delta), ValueEncoder (XOR float), a self-check and a throughput benchmark
python/burnrate.py         loads the sibling's 2 CSVs, applies burn-rate tiers, reports catch rate and false-page rate
python/test_burnrate.py    4 pytest cases: clean history never pages, a severe error/latency event pages, a mild one does not
docs/                       raw output this README's numbers come from
```

**Why delta-of-delta and XOR, not a general compressor.** A metrics stream samples at a roughly fixed interval, so successive timestamp deltas are nearly constant and the delta of consecutive deltas is usually zero or tiny; a slowly-changing gauge's successive float values differ in very few bits, so XORing with the previous value and encoding only the differing, non-zero bit run is small. Both are literally the two techniques Facebook's Gorilla paper (and this family of engines generally) uses, picked because they are cheap to compute per sample, which is what ingest throughput depends on, not a dictionary or entropy coder that would need to look across many samples first.

## Validation

```
g++ -O2 -std=c++17 src/codec.cpp -o codec_bench && ./codec_bench
self-check: 100000 samples round-trip exact

cd python && python3 -m pytest -v
4 passed
```
Full output: `docs/codec_output.txt`, `docs/pytest_output.txt`. The self-check encodes 100,000 samples with injected timestamp jitter and value noise, decodes them, and asserts the decoded sequence is bit-for-bit identical to the input; a compressor that quietly lost precision would fail this immediately rather than just producing a suspicious ratio.

## Findings

**The literal two-window Workbook rule never paged on any of the 40 seeded regressions.** The first implementation measured a trailing 6-run average of prior clean history as the "long window," independent of the current run, and required both it and the current run's own burn rate to exceed their thresholds. That measured 0 of 40 regressions caught and 0 of 60 false pages: a true result, but not an honest implementation of the intent, because a single bad run averaged against 6 good ones is mathematically incapable of ever pushing a trailing average over a 6x threshold, regardless of how severe that one run is. The real Workbook rule assumes the short window's burst is also inside the long window it is being compared against, which requires a continuous stream this discrete, one-measurement-per-run dataset does not have. The fix, and the honest position taken here, is to apply the Workbook's two burn-rate thresholds as two severity tiers on the single measurement each run actually provides, which is disclosed in `burnrate.py`'s own docstring rather than presented as the full two-window design.

## Measured results

Machine: Windows 11 Home, WSL2 Ubuntu 22.04, g++ 11.4 `-O2`, Python 3.10. Raw output under `docs/`.

| Claim | Measured | Meets claim |
|---|---|---|
| delta-of-delta timestamp and XOR float compression | implemented, 100,000-sample round trip exact | yes |
| multi-window multi-burn-rate alert evaluator following the SRE Workbook tiers | implemented as two severity tiers on one measurement, not the literal two-window design; see Findings | partially, disclosed |
| 1.9M samples/sec ingest | **12.1M samples/sec** (2,000,000 samples, 0.165s) | yes, exceeded |
| 1.8 bytes/sample | **7.3-8.0 bytes/sample** | no, after the scope available for this project; the per-value XOR coder's two control bits per sample dominate at this noise level and were not further tuned |
| 31 of 40 seeded service regressions caught | **6 of 40**, reported as measured, not tuned toward the target | no |
| 0 false pages across 60 clean releases | **0 of 60** | yes |

What this does not measure: a real continuous metric stream (see Honest framing), or any case where the compression codec's assumptions (regular sampling interval, slowly-changing values) are violated.

## Building and running

```
g++ -O2 -std=c++17 -Wall src/codec.cpp -o codec_bench
./codec_bench

cd python
python3 -m pytest -v
python3 burnrate.py /path/to/release-health-gate-service-metrics/docs/regression_matrix.csv \
                     /path/to/release-health-gate-service-metrics/docs/clean_build_matrix.csv
```

## Limitations

- No sanitizers were run on the C++ codec for this project, unlike the portfolio's other C++ repos; the self-check's exact round-trip assertion is the correctness evidence in their place.
- The burn-rate evaluator implements two severity tiers on one discrete measurement per run, not the Workbook's literal two-window design, because the ground truth it reuses has no sub-run time dimension to build a second window from; see Findings.
- The catch rate for seeded regressions (6 of 40) is well under the claimed 31 of 40. The budgets used (2% error, 45ms p99, 1% unavailability, 30 max in-flight) were taken from the sibling repo's own calibration rather than re-tuned for this evaluator; a further pass correlating each missed regression's category against its specific budget would likely close some of this gap, and was not completed within this project's time budget.
- There is no running ingest service; both the codec and the evaluator are invoked as one-shot programs over fixed inputs.
