# jev-pairs

**Deduplicate, cluster, link, and find contradictions across corpora with measurable blocking and a deterministic low-cost cascade.**

[![Tests](https://github.com/gbesse/jev-pairs/actions/workflows/test.yml/badge.svg)](https://github.com/gbesse/jev-pairs/actions/workflows/test.yml) ![MIT](https://img.shields.io/badge/license-MIT-blue) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![Public alpha](https://img.shields.io/badge/status-public_alpha-orange)

## 30-second offline quick start

```sh
git clone https://github.com/gbesse/jev-pairs.git && cd jev-pairs
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
python -m examples.offline_demo
```

Fixtures are synthetic, not measured Jev output.

## Audit a blocking rule offline

Run `python -m examples.blocking_audit` to compare candidate counts and labeled-match recall across three blocking settings on a synthetic product catalog. The JSON output highlights the trade-off: a stricter rule can save pair judgments while silently dropping known matches. Replace the fixture and its labeled pairs with a reviewed sample from your own corpus before choosing a rule; these results are not a quality benchmark.

## Call real Jev

Set `TYPESAFE_API_KEY` before supplying a reviewed provider adapter. Paid requests should go to `api.typesafe.ai`; this alpha leaves its live CLI adapter unwired rather than implying an unverified network path. `python scripts/live_smoke.py` reports that boundary and makes zero requests.

## Library and CLI

`dedupe(items, rule)`, `cluster`, `link`, and `contradict` return groups, judged/skipped pairs, conflicts, cache, and cost. A rule contains `id`, `version`, `statement`, `true`, `false`, and `key_fields`. Run `jev-pairs estimate items.json --rule rule.json`; operational commands accept `--fake`, `--pack`, and `--budget-usd`.

## How it decides

Optional exact, normalized, shared-token, sorted-neighbourhood and length blockers cut candidates. The illustrative cascade treats normalized identity as a match, token overlap at or above `certain_above=0.9` as a match, and at or below `certain_below=0.15` as a non-match. Only the band is judged against the rule statement. Complete linkage is the default and violating triangles are reported. See [the method](docs/method.md).

## Boundaries

Blocking can lose true pairs; measure that on labeled samples. Packing can degrade results because irrelevant state is a known model weakness. Defaults are illustrative, not calibrated. No benchmark or quality guarantee is claimed. The in-memory cache should be persisted by integrators. Incremental reuse comes from supplying the prior cache; existing cluster assignments are advisory rather than immutable.

## Validation

Run `python -m compileall -q src tests`, `python -m unittest discover -s tests`, and `python -m examples.offline_demo`. CI repeats these on Python 3.11 and 3.13.

## Related projects

[DecisionPacks](https://github.com/gbesse/decisionpacks), [Question Forge](https://github.com/gbesse/question-forge), and [jev-rerank-server](https://github.com/gbesse/jev-rerank-server) cover reusable rules, question design, and ranked retrieval.

Independent project; not affiliated with TypeSafe AI. [API documentation](https://docs.typesafe.ai/api) · [Jev 1.13 model notes](https://docs.typesafe.ai/model-jaggedness/jev-1.13/)
