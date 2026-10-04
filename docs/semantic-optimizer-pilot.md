# Semantic Optimizer: bounded empirical pair-plan pilot

This increment implements **pairwise plan selection**, not a general SQL query
optimizer. The runtime remains stdlib-only. Local, Jev, and frontier adapters can
be supplied through `PairEngine`, but this release creates no live adapter and
its CLI demonstration uses `FakeJev` only.

## API and measured boundary

`PairPlan` declares a blocker, overlap cascade, semantic engine and decision
threshold. `run_pair_plan` executes it with an integer cost-unit budget, explicit
abstentions when the budget is exhausted, and an engine-version/full-rule cache.
Only ids and rule key fields reach the engine. Its response must contain exactly
one valid probability per requested pair. The cascade is a **heuristic**, not a
claim that probability 0/1 is calibrated or that matching strings prove identity.

`select_pair_plan` chooses the cheapest empirically feasible candidate on tuning
labels. Its budget covers **all** candidate evaluations, not each separately.
Cache savings do not make a plan look free: ranking uses projected cold-cache
cost, in caller-supplied integer units per semantic pair, not dollars or measured
latency. Candidate order can matter when the global tuning budget is insufficient.
All candidate configuration and label coverage validates before the first call.

Every possible pair needs an explicit human `match` label, including pairs removed
by blockers. Those lost positives count as false negatives. Deferred positives
also count as unrecovered matches and abstention is reported separately. No absent
label is interpreted as false. Precision/recall are null if their denominators
are absent, and such a plan cannot pass a quality gate. No feasible candidate
returns `no_feasible_plan`, never a falsely qualified cheapest fallback.

`validate_pair_plan` freezes the selection and evaluates a separate labeled
holdout. Overlapping ids or normalized tuning content under new ids are rejected;
the rule, engine versions, prices and artifact fingerprint must be unchanged.
Failure does **not** trigger reselection on holdout labels. Keep that holdout sealed
from further tuning and split related documents/entities as groups; id separation
alone is not statistical independence. Fingerprints are integrity checks, not
signatures or resistance to malicious relabeling. Labels must be genuine human
judgments; the program cannot authenticate the annotator.

Provider implementations are caller-owned trusted code. Cost units are only a
bound on declared costs; an adapter's internal requests/retries are outside this
accounting. Failed provider responses abort rather than silently buying more.
The pilot enumerates O(n²) pairs and requires a fully labeled small corpus. It
does not yet solve large-scale recall estimation, adaptive blocking, or arbitrary
filter/map/rank queries.

## Reproduce offline

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m examples.semantic_optimizer
PYTHONPATH=src python3 -m jev_pairs optimizer-demo
```

The synthetic demo rejects a cheap exact-name blocker that loses the true pair,
chooses a cheaper fixture engine on tuning data, and evaluates that exact plan on
disjoint held-out fixtures. It proves accounting and isolation mechanics only.

## Research and go/no-go protocol

Compare full semantic judgment, deterministic overlap, each fixed cascade and
the selector on a human-annotated catalog split by entities. Report precision,
recall including blocking loss, abstention, provider calls, actual cost and p95
latency; estimate uncertainty and repeat across independent corpora. Count tuning,
labeling, caching and human-review costs as well as inference. Tune once; publish
held-out failures and malformed provider cases, not only a favorable run.

For broader work, [LOTUS](https://arxiv.org/abs/2407.11418) is a primary baseline;
[SemBaker (2026)](https://arxiv.org/abs/2608.06677) investigates compilation, and
[SemBench](https://arxiv.org/abs/2511.01716) offers public semantic-query workloads.
None has been run by this pilot. A SOTA claim requires reproducible comparisons,
not this fixture. Proceed only if savings survive held-out quality constraints
and labeling/tuning overhead. No technical improvement on real data is claimed.
