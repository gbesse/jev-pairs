import unittest
from jev_pairs.core import audit_cluster_links
class ClusterLinkTests(unittest.TestCase):
 def test_transitive_contradiction(self):
  x=audit_cluster_links(['a','b','c'],[dict(left='a',right='b',probability=.9),dict(left='b',right='c',probability=.9),dict(left='a',right='c',probability=.1)])['components'][0];self.assertEqual(x['contradicting_pairs'],[['a','c']]);self.assertFalse(x['pairwise_confirmed'])
 def test_missing_pair(self):
  x=audit_cluster_links(['a','b','c'],[dict(left='a',right='b',probability=.9),dict(left='b',right='c',probability=.9)])['components'][0];self.assertEqual(x['unjudged_pairs'],[['a','c']])
 def test_duplicate_reversed(self):
  with self.assertRaises(ValueError):audit_cluster_links(['a','b'],[dict(left='a',right='b',probability=.9),dict(left='b',right='a',probability=.9)])
