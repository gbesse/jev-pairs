# Purpose: Exercise blockers, cascade routing, cache symmetry, clustering, packing and conflicts.
import unittest
from jev_pairs import *
RULE={"id":"r","version":"1","statement":"same","true":{},"false":{},"key_fields":["name"]}
class PairTests(unittest.TestCase):
 def test_blockers_and_loss(self):
  items=[{"name":"Alpha one"},{"name":"Alpha two"},{"name":"Beta"}]
  self.assertEqual(candidate_pairs(items,RULE,{"token_overlap":.3}),[(0,1)])
  report=blocking_report(items,RULE,{"exact_key":True},[(0,1)]);self.assertEqual(report["known_matches_dropped"],1)
 def test_cascade_and_call_count(self):
  items=[{"id":"a","name":"same"},{"id":"b","name":"same"},{"id":"c","name":"same extra"},{"id":"d","name":"zzz"}];fake=FakeJev({"a|c":.8,"b|c":.8})
  result=dedupe(items,RULE,fake,certain_below=.1,certain_above=.99,pack=2)
  self.assertEqual(len(fake.calls),1);self.assertEqual(sum(len(x) for x in fake.calls),2);self.assertTrue(any(x["source"]=="cascade-match" for x in result["judged_pairs"]))
 def test_symmetric_key(self):
  a,b={"name":"A"},{"name":"B"};self.assertEqual(pair_key(a,b,RULE),pair_key(b,a,RULE))
 def test_groups_and_triangle(self):
  judged=[{"left":0,"right":1,"probability":.9},{"left":1,"right":2,"probability":.9},{"left":0,"right":2,"probability":.1}]
  self.assertEqual(len(conflicts(judged)),1)
  result=dedupe([{"name":"a"},{"name":"a"},{"name":"b"}],RULE,FakeJev(),certain_above=.9,linkage="complete");self.assertIn([0,1],result["groups"])
 def test_estimate_arithmetic_and_determinism(self):
  items=[{"name":"red shoe"},{"name":"red shoes"},{"name":"hat"}];a=estimate(items,RULE);b=estimate(items,RULE)
  self.assertEqual(a,b);self.assertAlmostEqual(a["estimated_cost_usd"],a["estimated_input_tokens"]*.042/1_000_000)
 def test_incremental_cache_reuse(self):
  items=[{"id":"a","name":"red shoe"},{"id":"b","name":"red shoes"}];fake=FakeJev({"a|b":.8});cache={}
  dedupe(items,RULE,fake,cache=cache,certain_below=0,certain_above=1);calls=len(fake.calls)
  dedupe(items+[{"id":"c","name":"red boot"}],RULE,fake,cache=cache,certain_below=0,certain_above=1)
  self.assertEqual(len(fake.calls)-calls,2)
if __name__=="__main__":unittest.main()
