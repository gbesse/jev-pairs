"""Offline empirical pair-plan selection with a separate held-out validation gate.

Costs are caller-supplied integer units, not vendor prices. No live adapter is
created. Labels are required for ALL pairs, including those removed by blocking.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from itertools import combinations
import json
import math

from .core import candidate_pairs, normalize, overlap


def _hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _unit(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _probability(value):
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("probability must be finite and between zero and one")
    return float(value)


@dataclass(frozen=True)
class PairPlan:
    name: str
    engine: str
    blocking: dict = field(default_factory=dict)
    nonmatch_at: float = 0.15
    match_at: float = 0.9
    threshold: float = 0.5


@dataclass(frozen=True)
class PairEngine:
    name: str
    version: str
    cost_units_per_pair: int
    provider: object


def _prepare(items, rule):
    if not isinstance(items, list) or not isinstance(rule, dict):
        raise ValueError("items must be a list and rule an object")
    fields = rule.get("key_fields")
    if not isinstance(fields, list) or not fields or any(not isinstance(key, str) or not key or key == "id" for key in fields) or len(set(fields)) != len(fields):
        raise ValueError("key_fields must be unique non-empty field names, excluding id")
    if any(not isinstance(rule.get(key), str) or not rule[key] for key in ("id", "version", "statement")):
        raise ValueError("rule needs id, version and statement")
    ids = set()
    prepared = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or item["id"] in ids:
            raise ValueError("items need unique non-empty string ids")
        ids.add(item["id"])
        if any(not isinstance(item.get(key), str) or not normalize(item[key]) for key in fields):
            raise ValueError("all key fields need non-empty text")
        # Only whitelisted semantic fields and ids reach engines; labels/metadata do not.
        prepared.append({"id": item["id"], **{key: item[key] for key in fields}})
    public_rule = {key: deepcopy(rule[key]) for key in ("id", "version", "statement", "key_fields")}
    for key in ("true", "false"):
        if key in rule:
            public_rule[key] = deepcopy(rule[key])
    return sorted(prepared, key=lambda item: item["id"]), public_rule


def _validate_plan(plan, rule):
    if not isinstance(plan, PairPlan) or not isinstance(plan.name, str) or not plan.name or not isinstance(plan.engine, str) or not plan.engine:
        raise ValueError("plan needs a name and engine")
    if not 0 <= _probability(plan.nonmatch_at) < _probability(plan.match_at) <= 1:
        raise ValueError("nonmatch_at must be below match_at")
    _probability(plan.threshold)
    if not isinstance(plan.blocking, dict):
        raise ValueError("blocking must be an object")
    allowed = {"exact_key", "normalized_key", "token_overlap", "length_ratio", "sorted_neighbourhood"}
    if set(plan.blocking) - allowed:
        raise ValueError("unknown blocking option")
    for key in ("exact_key", "normalized_key"):
        if key in plan.blocking and type(plan.blocking[key]) is not bool:
            raise ValueError("key blockers must be booleans")
    for key in ("token_overlap", "length_ratio"):
        if key in plan.blocking:
            _probability(plan.blocking[key])
    if "sorted_neighbourhood" in plan.blocking:
        config = plan.blocking["sorted_neighbourhood"]
        if not isinstance(config, dict) or set(config) - {"key", "window"} or config.get("key") not in rule["key_fields"]:
            raise ValueError("invalid sorted_neighbourhood key")
        window = config.get("window", 3)
        if type(window) is not int or window < 2:
            raise ValueError("sorted_neighbourhood window must be at least two")


def _engine_map(engines):
    if not isinstance(engines, list):
        raise ValueError("engines must be a list")
    result = {}
    for engine in engines:
        if not isinstance(engine, PairEngine) or not isinstance(engine.name, str) or not engine.name or engine.name in result or not isinstance(engine.version, str) or not engine.version:
            raise ValueError("engines need unique names and explicit versions")
        _unit(engine.cost_units_per_pair, "cost_units_per_pair")
        if not callable(getattr(engine.provider, "judge", None)):
            raise ValueError("engine provider must implement judge")
        result[engine.name] = engine
    return result


def _signatures(engines):
    return sorted([{"name": engine.name, "version": engine.version, "cost_units_per_pair": engine.cost_units_per_pair}
                   for engine in engines], key=lambda entry: entry["name"])


def _labels(items, labels):
    if not isinstance(labels, list):
        raise ValueError("labels must be a list")
    expected = {tuple(sorted((a["id"], b["id"]))) for a, b in combinations(items, 2)}
    truth = {}
    for label in labels:
        if not isinstance(label, dict) or not isinstance(label.get("left"), str) or not isinstance(label.get("right"), str) or type(label.get("match")) is not bool:
            raise ValueError("labels need left/right ids and an explicit boolean match")
        key = tuple(sorted((label["left"], label["right"])))
        if key not in expected or key in truth:
            raise ValueError("unknown, self or duplicate labeled pair")
        truth[key] = label["match"]
    if set(truth) != expected:
        raise ValueError("complete pair labels required, including blocked and deferred pairs")
    return truth


def _metrics(rows, truth):
    tp = fp = fn = tn = abstained = blocked_matches = 0
    for row in rows:
        actual = truth[tuple(sorted((row["left"], row["right"])))]
        predicted = row["decision"] == "match"
        if predicted:
            if actual: tp += 1
            else: fp += 1
        elif actual:
            fn += 1
            if row["decision"] == "blocked": blocked_matches += 1
        elif row["decision"] != "abstain": tn += 1
        if row["decision"] == "abstain": abstained += 1
    return {"true_positives": tp, "false_positives": fp, "false_negatives": fn,
            "true_negatives": tn, "blocked_true_matches": blocked_matches,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "abstentions": abstained, "abstention_rate": abstained / len(rows) if rows else None}


def run_pair_plan(items, rule, plan, engines, *, budget_units, cache=None):
    """Execute a configured pair plan; budget-deferred pairs remain explicit abstentions."""
    _unit(budget_units, "budget_units")
    prepared, public_rule = _prepare(items, rule)
    _validate_plan(plan, public_rule)
    engine_by_name = _engine_map(engines)
    if plan.engine not in engine_by_name:
        raise ValueError("unknown plan engine")
    engine = engine_by_name[plan.engine]
    cache = cache if cache is not None else {}
    candidates = set(candidate_pairs(prepared, public_rule, plan.blocking))
    spent = calls = projected = 0
    rows = []
    for i, j in combinations(range(len(prepared)), 2):
        a, b = prepared[i], prepared[j]
        probability = None
        if (i, j) not in candidates:
            decision, source = "blocked", "blocking"
        else:
            score = overlap(a, b, public_rule["key_fields"])
            identical = all(normalize(a[key]) == normalize(b[key]) for key in public_rule["key_fields"])
            if identical or score >= plan.match_at:
                probability, source = 1.0, "heuristic-match"
            elif score <= plan.nonmatch_at:
                probability, source = 0.0, "heuristic-nonmatch"
            else:
                projected += engine.cost_units_per_pair
                key = _hash({"engine": {"name": engine.name, "version": engine.version}, "rule": public_rule,
                             "pair": sorted([a, b], key=lambda item: item["id"])})
                if key in cache:
                    probability, source = _probability(cache[key]), "cache"
                elif spent + engine.cost_units_per_pair <= budget_units:
                    # Count the attempt even if a provider fails; never swallow a malformed response.
                    spent += engine.cost_units_per_pair
                    calls += 1
                    answers = engine.provider.judge([(deepcopy(a), deepcopy(b))], deepcopy(public_rule))
                    if not isinstance(answers, (list, tuple)) or len(answers) != 1:
                        raise ValueError("engine must return exactly one probability per pair")
                    probability, source = _probability(answers[0]), "engine"
                    cache[key] = probability
                else:
                    source = "budget"
            decision = "abstain" if probability is None else "match" if probability >= plan.threshold else "nonmatch"
        rows.append({"left": a["id"], "right": b["id"], "decision": decision, "source": source,
                     "probability": probability})
    return {"plan": asdict(plan), "rows": rows, "spent_cost_units": spent,
            "provider_calls": calls, "projected_cold_cost_units": projected, "candidate_pairs": len(candidates)}


def _constraints(min_precision, min_recall, max_abstention_rate):
    return {"min_precision": _probability(min_precision), "min_recall": _probability(min_recall),
            "max_abstention_rate": _probability(max_abstention_rate)}


def _passes(metrics, constraints):
    return (metrics["precision"] is not None and metrics["recall"] is not None and metrics["abstention_rate"] is not None
            and metrics["precision"] >= constraints["min_precision"] and metrics["recall"] >= constraints["min_recall"]
            and metrics["abstention_rate"] <= constraints["max_abstention_rate"])


def _content_fingerprints(items, rule):
    return sorted({_hash({key: normalize(item[key]) for key in rule["key_fields"]}) for item in items})


def select_pair_plan(items, rule, labels, plans, engines, *, budget_units,
                     min_precision=0.95, min_recall=0.95, max_abstention_rate=0.0):
    """Select from tuning labels only. This is an empirical selector, not a risk certificate."""
    _unit(budget_units, "budget_units")
    constraints = _constraints(min_precision, min_recall, max_abstention_rate)
    prepared, public_rule = _prepare(items, rule)
    truth = _labels(prepared, labels)
    if not isinstance(plans, list) or not plans or any(not isinstance(plan, PairPlan) for plan in plans) or len({plan.name for plan in plans}) != len(plans):
        raise ValueError("plans need unique names and at least one candidate")
    engine_by_name = _engine_map(engines)
    # Validate every candidate before any potentially paid provider call.
    for plan in plans:
        _validate_plan(plan, public_rule)
        if plan.engine not in engine_by_name:
            raise ValueError("unknown plan engine")
    spent = calls = 0
    cache, evaluations = {}, []
    for plan in plans:
        result = run_pair_plan(prepared, public_rule, plan, engines, budget_units=budget_units - spent, cache=cache)
        spent += result["spent_cost_units"]
        calls += result["provider_calls"]
        metrics = _metrics(result["rows"], truth)
        evaluations.append({"plan": asdict(plan), "metrics": metrics, "feasible": _passes(metrics, constraints),
                            "projected_cold_cost_units": result["projected_cold_cost_units"],
                            "spent_cost_units": result["spent_cost_units"], "provider_calls": result["provider_calls"],
                            "candidate_pairs": result["candidate_pairs"]})
    feasible = [evaluation for evaluation in evaluations if evaluation["feasible"]]
    best = min(feasible, key=lambda evaluation: (evaluation["projected_cold_cost_units"],
               -evaluation["metrics"]["recall"], -evaluation["metrics"]["precision"], evaluation["plan"]["name"])) if feasible else None
    body = {"schema_version": 1, "method": "empirical-pair-planner-v1",
            "status": "selected" if best else "no_feasible_plan", "selected_plan": best["plan"] if best else None,
            "constraints": constraints, "rule_fingerprint": _hash(public_rule), "engines": _signatures(engines),
            "tuning_ids": sorted(item["id"] for item in prepared),
            "tuning_content_fingerprints": _content_fingerprints(prepared, public_rule),
            "tuning_fingerprint": _hash({"items": prepared, "labels": labels}),
            "budget_units": budget_units, "spent_cost_units": spent, "provider_calls": calls,
            "evaluations": evaluations}
    return {**body, "selection_fingerprint": _hash(body)}


def validate_pair_plan(selection, items, rule, labels, engines, *, budget_units):
    """Freeze the selected plan: held-out labels never cause reselection or threshold tuning."""
    _unit(budget_units, "budget_units")
    if not isinstance(selection, dict):
        raise ValueError("selection must be an object")
    body = {key: value for key, value in selection.items() if key != "selection_fingerprint"}
    if selection.get("schema_version") != 1 or selection.get("method") != "empirical-pair-planner-v1" or selection.get("selection_fingerprint") != _hash(body):
        raise ValueError("invalid or changed selection artifact")
    if selection["status"] != "selected" or not selection["selected_plan"]:
        raise ValueError("no feasible selected plan to validate")
    prepared, public_rule = _prepare(items, rule)
    truth = _labels(prepared, labels)
    if selection["rule_fingerprint"] != _hash(public_rule) or selection["engines"] != _signatures(engines):
        raise ValueError("rule or engine version/cost changed after selection")
    if set(selection["tuning_ids"]) & {item["id"] for item in prepared}:
        raise ValueError("holdout ids overlap tuning ids")
    if set(selection["tuning_content_fingerprints"]) & set(_content_fingerprints(prepared, public_rule)):
        raise ValueError("holdout contains normalized tuning content under different ids")
    plan = PairPlan(**selection["selected_plan"])
    result = run_pair_plan(prepared, public_rule, plan, engines, budget_units=budget_units)
    metrics = _metrics(result["rows"], truth)
    return {"schema_version": 1, "selection_fingerprint": selection["selection_fingerprint"],
            "holdout_fingerprint": _hash({"items": prepared, "labels": labels}), "selected_plan": asdict(plan),
            "passed": _passes(metrics, selection["constraints"]), "metrics": metrics,
            "spent_cost_units": result["spent_cost_units"], "provider_calls": result["provider_calls"],
            "projected_cold_cost_units": result["projected_cold_cost_units"]}
