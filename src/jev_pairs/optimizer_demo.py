"""Installed offline demonstration; entry point shared with the repository example."""
from itertools import combinations
from .core import FakeJev
from .optimizer import PairEngine, PairPlan, select_pair_plan, validate_pair_plan


def demo():
    rule = {"id": "product", "version": "pilot-v1", "statement": "Same product", "key_fields": ["name"]}
    tuning = [{"id": "a", "name": "Red running shoe"}, {"id": "b", "name": "Red running shoes"},
              {"id": "c", "name": "Blue winter coat"}]
    holdout = [{"id": "d", "name": "Green desk lamp"}, {"id": "e", "name": "Green desk lamps"},
               {"id": "f", "name": "Yellow beach hat"}]
    def labels(items, match):
        return [{"left": a["id"], "right": b["id"], "match": (a["id"], b["id"]) == match}
                for a, b in combinations(items, 2)]
    engines = [PairEngine("small-fixture", "v1", 1, FakeJev({"a|b": 0.9, "d|e": 0.9})),
               PairEngine("large-fixture", "v1", 10, FakeJev({"a|b": 0.9, "d|e": 0.9}))]
    plans = [PairPlan("too-strict", "small-fixture", {"exact_key": True}),
             PairPlan("small", "small-fixture"), PairPlan("large", "large-fixture")]
    selection = select_pair_plan(tuning, rule, labels(tuning, ("a", "b")), plans, engines, budget_units=20)
    validation = validate_pair_plan(selection, holdout, rule, labels(holdout, ("d", "e")), engines, budget_units=10)
    assert selection["selected_plan"]["name"] == "small"
    assert validation["passed"]
    assert selection["evaluations"][0]["metrics"]["blocked_true_matches"] == 1
    return {"synthetic": True, "network_calls": 0, "selection": selection, "holdout": validation}
