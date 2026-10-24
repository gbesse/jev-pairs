import unittest
from jev_pairs.core import dedupe,pair_key
class Provider:
 def __init__(self,values):self.values=values
 def judge(self,pairs,rule):return self.values
class BatchContract(unittest.TestCase):
 def setUp(self):
  self.items=[{'id':i,'name':name}for i,name in enumerate(['red blue','red green','red yellow'])];self.rule={'version':'test','key_fields':['name']}
 def run_batch(self,values,cache):return dedupe(self.items,self.rule,Provider(values),cache=cache,certain_below=0,certain_above=1,pack=3)
 def test_invalid_batch_is_not_partially_cached(self):
  for values in [[.2],[.2,.3,.4,.5],[.2,float('nan'),.4],[.2,True,.4],[.2,1.1,.4],[.2,-.1,.4],iter([.2,.3,.4])]:
   cache={}
   with self.assertRaises(ValueError):self.run_batch(values,cache)
   self.assertEqual(cache,{})
 def test_valid_boundaries_and_cached_probability_contract(self):
  cache={};result=self.run_batch([0,.5,1],cache);self.assertEqual(len(cache),3);self.assertEqual([x['probability']for x in result['judged_pairs']],[0,.5,1])
  key=pair_key(self.items[0],self.items[1],self.rule);cache[key]=True
  with self.assertRaises(ValueError):self.run_batch([],cache)
