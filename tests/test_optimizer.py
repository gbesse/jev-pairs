import unittest
import json
import os
import subprocess
import sys
from copy import deepcopy
from itertools import combinations
from jev_pairs import PairEngine, PairPlan, FakeJev, run_pair_plan, select_pair_plan, validate_pair_plan

RULE = {"id": "p", "version": "1", "statement": "Same product", "key_fields": ["name"]}
ITEMS = [{"id": "a", "name": "Red running shoe", "private_label": True},
         {"id": "b", "name": "Red running shoes"}, {"id": "c", "name": "Blue coat"}]
HOLDOUT = [{"id": "d", "name": "Green desk lamp"}, {"id": "e", "name": "Green desk lamps"},
           {"id": "f", "name": "Yellow hat"}]


def labels(items, match):
    return [{"left": a["id"], "right": b["id"], "match": (a["id"], b["id"]) == match}
            for a, b in combinations(items, 2)]


class OptimizerTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeJev({"a|b": 0.9, "d|e": 0.9})
        self.engines = [PairEngine("small", "v1", 1, self.fake), PairEngine("large", "v1", 10, self.fake)]
        self.plans = [PairPlan("strict", "small", {"exact_key": True}), PairPlan("small", "small"), PairPlan("large", "large")]

    def select(self, **kwargs):
        return select_pair_plan(ITEMS, RULE, labels(ITEMS, ("a", "b")), self.plans, self.engines, budget_units=kwargs.pop("budget_units", 20), **kwargs)

    def test_cheapest_feasible_not_cheapest_broken_blocker(self):
        result = self.select()
        self.assertEqual(result["selected_plan"]["name"], "small")
        strict = result["evaluations"][0]
        self.assertFalse(strict["feasible"])
        self.assertEqual(strict["metrics"]["blocked_true_matches"], 1)
        self.assertEqual(strict["metrics"]["recall"], 0)
        self.assertEqual(result["spent_cost_units"], 11)

    def test_selection_total_budget_covers_all_candidates(self):
        result = self.select(budget_units=0)
        self.assertEqual(result["status"], "no_feasible_plan")
        self.assertIsNone(result["selected_plan"])
        self.assertEqual(self.fake.calls, [])
        self.assertTrue(any(e["metrics"]["abstentions"] for e in result["evaluations"]))
        with self.assertRaises(ValueError):
            validate_pair_plan(result, HOLDOUT, RULE, labels(HOLDOUT, ("d", "e")), self.engines, budget_units=10)

    def test_labels_and_non_whitelisted_metadata_never_reach_engine(self):
        self.select()
        for batch in self.fake.calls:
            for a, b in batch:
                self.assertEqual(set(a), {"id", "name"})
                self.assertEqual(set(b), {"id", "name"})

    def test_holdout_pass_and_fail_do_not_reselect(self):
        selection = self.select()
        before = deepcopy(selection)
        good = validate_pair_plan(selection, HOLDOUT, RULE, labels(HOLDOUT, ("d", "e")), self.engines, budget_units=10)
        self.assertTrue(good["passed"])
        bad = validate_pair_plan(selection, HOLDOUT, RULE, labels(HOLDOUT, ("d", "f")), self.engines, budget_units=10)
        self.assertFalse(bad["passed"])
        self.assertEqual(bad["selected_plan"]["name"], "small")
        self.assertEqual(selection, before)

    def test_holdout_rejects_ids_and_renamed_identical_content(self):
        selection = self.select()
        with self.assertRaisesRegex(ValueError, "ids overlap"):
            validate_pair_plan(selection, ITEMS, RULE, labels(ITEMS, ("a", "b")), self.engines, budget_units=10)
        renamed = [{**item, "id": f"new-{item['id']}"} for item in ITEMS]
        with self.assertRaisesRegex(ValueError, "normalized tuning content"):
            validate_pair_plan(selection, renamed, RULE, labels(renamed, ("new-a", "new-b")), self.engines, budget_units=10)

    def test_complete_labels_required_even_for_blocked_pairs_before_calls(self):
        for bad in [[], labels(ITEMS, ("a", "b"))[:-1], labels(ITEMS, ("a", "b")) * 2,
                    [{"left": "a", "right": "x", "match": True}], [{"left": "a", "right": "b", "match": "false"}]]:
            with self.assertRaises(ValueError):
                select_pair_plan(ITEMS, RULE, bad, self.plans, self.engines, budget_units=20)
        self.assertEqual(self.fake.calls, [])

    def test_invalid_candidate_configuration_cannot_follow_a_paid_call(self):
        for bad in [PairPlan("bad", "unknown"), PairPlan("bad", "small", {"unknown": True}),
                    PairPlan("bad", "small", match_at=0.1, nonmatch_at=0.9),
                    PairPlan("bad", "small", {"token_overlap": float("nan")}),
                    PairPlan("bad", "small", {"sorted_neighbourhood": {"key": "name", "window": 1}})]:
            with self.assertRaises(ValueError):
                select_pair_plan(ITEMS, RULE, labels(ITEMS, ("a", "b")), [self.plans[1], bad], self.engines, budget_units=20)
        self.assertEqual(self.fake.calls, [])

    def test_cache_identity_includes_full_rule_and_engine_version(self):
        cache = {}
        run_pair_plan(ITEMS, RULE, self.plans[1], self.engines, budget_units=10, cache=cache)
        run_pair_plan(ITEMS, RULE, self.plans[1], self.engines, budget_units=0, cache=cache)
        self.assertEqual(len(self.fake.calls), 1)
        changed_rule = {**RULE, "statement": "Different semantic relation"}
        run_pair_plan(ITEMS, changed_rule, self.plans[1], self.engines, budget_units=10, cache=cache)
        self.assertEqual(len(self.fake.calls), 2)
        changed = [PairEngine("small", "v2", 1, self.fake)]
        run_pair_plan(ITEMS, RULE, self.plans[1], changed, budget_units=10, cache=cache)
        self.assertEqual(len(self.fake.calls), 3)

    def test_artifact_mutations_rule_changes_and_engine_changes_fail(self):
        selection = self.select()
        kwargs = dict(items=HOLDOUT, rule=RULE, labels=labels(HOLDOUT, ("d", "e")), engines=self.engines, budget_units=10)
        changed = deepcopy(selection); changed["constraints"]["min_recall"] = 0
        with self.assertRaisesRegex(ValueError, "changed selection"):
            validate_pair_plan(changed, **kwargs)
        with self.assertRaisesRegex(ValueError, "rule or engine"):
            validate_pair_plan(selection, **{**kwargs, "rule": {**RULE, "version": "2"}})
        with self.assertRaisesRegex(ValueError, "rule or engine"):
            validate_pair_plan(selection, **{**kwargs, "engines": [PairEngine("small", "v2", 1, self.fake)]})

    def test_bad_provider_responses_and_bad_cache_fail_closed(self):
        class Bad:
            def __init__(self, response): self.response = response
            def judge(self, pairs, rule): return self.response
        for response in [[], [0.5, 0.5], [float("nan")], [2], [True], ["0.5"]]:
            with self.assertRaises(ValueError):
                run_pair_plan(ITEMS, RULE, self.plans[1], [PairEngine("small", "v1", 1, Bad(response))], budget_units=10)
        cache = {}
        run_pair_plan(ITEMS, RULE, self.plans[1], self.engines, budget_units=10, cache=cache)
        cache[next(iter(cache))] = float("nan")
        with self.assertRaises(ValueError):
            run_pair_plan(ITEMS, RULE, self.plans[1], self.engines, budget_units=10, cache=cache)

    def test_missing_key_fields_duplicate_ids_bad_units_are_rejected(self):
        for bad in [[ITEMS[0], ITEMS[0]], [{"id": "a", "name": ""}], [{"id": "a"}]]:
            with self.assertRaises(ValueError):
                run_pair_plan(bad, RULE, self.plans[1], self.engines, budget_units=10)
        for budget in [-1, True, float("inf"), 0.5]:
            with self.assertRaises(ValueError): self.select(budget_units=budget)

    def test_order_independent_execution_and_no_unnecessary_purchase_on_cache_hit(self):
        cache = {}
        original = run_pair_plan(ITEMS, RULE, self.plans[1], self.engines, budget_units=10, cache=cache)
        reversed_result = run_pair_plan(list(reversed(ITEMS)), RULE, self.plans[1], self.engines, budget_units=0, cache=cache)
        self.assertEqual([row["decision"] for row in original["rows"]], [row["decision"] for row in reversed_result["rows"]])
        self.assertEqual(reversed_result["provider_calls"], 0)
        self.assertEqual(reversed_result["projected_cold_cost_units"], 1)

    def test_installed_module_cli_demo_and_unknown_demo_arguments(self):
        env = {**os.environ, "PYTHONPATH": "src"}
        result = subprocess.run([sys.executable, "-m", "jev_pairs", "optimizer-demo"], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["synthetic"])
        self.assertEqual(report["network_calls"], 0)
        self.assertTrue(report["holdout"]["passed"])
        bad = subprocess.run([sys.executable, "-m", "jev_pairs", "optimizer-demo", "--live"], capture_output=True, text=True, env=env)
        self.assertNotEqual(bad.returncode, 0)

    def test_generator_engines_and_nonplan_candidates_are_rejected_before_calls(self):
        with self.assertRaises(ValueError):
            run_pair_plan(ITEMS, RULE, self.plans[1], iter(self.engines), budget_units=10)
        with self.assertRaises(ValueError):
            select_pair_plan(ITEMS, RULE, labels(ITEMS, ("a", "b")), [self.plans[1], {}], self.engines, budget_units=20)
        self.assertEqual(self.fake.calls, [])


if __name__ == "__main__":
    unittest.main()
