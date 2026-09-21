# Purpose: Deterministic blocking/cascade and paid pair-judgment orchestration.
from __future__ import annotations
import hashlib, itertools, json, math, re

MODEL="jev-1.13.0"; PRICE=.042
def canonical(value): return json.dumps(value,sort_keys=True,separators=(",",":"))
def normalize(value): return " ".join(re.findall(r"[a-z0-9]+",str(value).lower()))
def item_hash(item,fields): return hashlib.sha256(canonical({k:item.get(k) for k in fields}).encode()).hexdigest()
def pair_key(left,right,rule):
    hashes=sorted([item_hash(left,rule["key_fields"]),item_hash(right,rule["key_fields"])])
    return hashlib.sha256(canonical({"model":MODEL,"rule":rule["version"],"pair":hashes}).encode()).hexdigest()
def _tokens(item,fields): return set(normalize(" ".join(str(item.get(k,"")) for k in fields)).split())
def overlap(left,right,fields):
    a,b=_tokens(left,fields),_tokens(right,fields); return len(a&b)/len(a|b) if a|b else 1
def _passes(a,b,fields,blocking):
    checks=[]
    if blocking.get("exact_key"): checks.append(any(a.get(k)==b.get(k) and a.get(k) not in {None,""} for k in fields))
    if blocking.get("normalized_key"): checks.append(any(normalize(a.get(k,""))==normalize(b.get(k,"")) and normalize(a.get(k,"")) for k in fields))
    if "token_overlap" in blocking: checks.append(overlap(a,b,fields)>=blocking["token_overlap"])
    if "length_ratio" in blocking:
        x,y=len(canonical(a)),len(canonical(b)); checks.append(min(x,y)/max(x,y,1)>=blocking["length_ratio"])
    return all(checks) if checks else True
def candidate_pairs(items,rule,blocking=None):
    blocking=blocking or {}; pairs=[]
    for i,j in itertools.combinations(range(len(items)),2):
        if _passes(items[i],items[j],rule["key_fields"],blocking): pairs.append((i,j))
    if "sorted_neighbourhood" in blocking:
        key=blocking["sorted_neighbourhood"]["key"]; window=blocking["sorted_neighbourhood"].get("window",3); allowed=set()
        order=sorted(range(len(items)),key=lambda i:normalize(items[i].get(key,"")))
        for p,i in enumerate(order):
            for j in order[p+1:p+window]: allowed.add(tuple(sorted((i,j))))
        pairs=[pair for pair in pairs if pair in allowed]
    return pairs
def blocking_report(items,rule,blocking=None,labeled_pairs=None):
    candidates=set(candidate_pairs(items,rule,blocking)); total=len(items)*(len(items)-1)//2
    truth={tuple(sorted(x)) for x in (labeled_pairs or [])}; kept=len(truth&candidates)
    return {"total_pairs":total,"candidate_pairs":len(candidates),"eliminated":total-len(candidates),
            "labeled_match_recall":kept/len(truth) if truth else None,"known_matches_dropped":len(truth-candidates)}
def estimate(items,rule,blocking=None,certain_below=.15,certain_above=.9):
    pairs=candidate_pairs(items,rule,blocking); counts={"identical":0,"certain_match":0,"certain_nonmatch":0,"to_buy":0}
    for i,j in pairs:
        exact=all(normalize(items[i].get(k,""))==normalize(items[j].get(k,"")) for k in rule["key_fields"]); score=overlap(items[i],items[j],rule["key_fields"])
        bucket="identical" if exact else "certain_match" if score>=certain_above else "certain_nonmatch" if score<=certain_below else "to_buy";counts[bucket]+=1
    tokens=sum(math.ceil(len(canonical({"left":items[i],"right":items[j]}))/4) for i,j in pairs)
    return {"items":len(items),"candidate_pairs":len(pairs),**counts,"estimated_input_tokens":tokens,"estimated_cost_usd":tokens*PRICE/1_000_000}
class FakeJev:
    """Fixture provider; keys are sorted id pairs joined with a pipe."""
    def __init__(self,fixtures=None):self.fixtures=fixtures or {};self.calls=[]
    def judge(self,pairs,rule):
        self.calls.append(pairs);return [self.fixtures.get("|".join(sorted([str(a.get("id")),str(b.get("id"))])),.5) for a,b in pairs]
def _judge(items,rule,provider,blocking,cache,certain_below,certain_above,pack,budget_usd):
    judged=[]; pending=[]; spent=0; skipped=[]
    for i,j in candidate_pairs(items,rule,blocking):
        a,b=items[i],items[j]; key=pair_key(a,b,rule); score=overlap(a,b,rule["key_fields"])
        exact=all(normalize(a.get(k,""))==normalize(b.get(k,"")) for k in rule["key_fields"])
        if key in cache: probability=cache[key];source="cache"
        elif exact or score>=certain_above: probability=1.;source="cascade-match"
        elif score<=certain_below: probability=0.;source="cascade-nonmatch"
        else: pending.append((i,j,key));continue
        judged.append({"left":i,"right":j,"probability":probability,"source":source})
    for start in range(0,len(pending),max(1,pack)):
        batch=pending[start:start+max(1,pack)]; states=[(items[i],items[j]) for i,j,_ in batch]
        cost=sum(math.ceil(len(canonical({"left":a,"right":b}))/4) for a,b in states)*PRICE/1_000_000
        if spent+cost>budget_usd: skipped.extend((i,j) for i,j,_ in batch);continue
        probabilities=provider.judge(states,rule);spent+=cost
        for (i,j,key),probability in zip(batch,probabilities):cache[key]=probability;judged.append({"left":i,"right":j,"probability":probability,"source":"jev"})
    return judged,skipped,{"estimated_cost_usd":spent,"bought_pairs":sum(x["source"]=="jev" for x in judged)}
def conflicts(judged,threshold=.5):
    matrix={(min(x["left"],x["right"]),max(x["left"],x["right"])):x["probability"] for x in judged};nodes=sorted({n for pair in matrix for n in pair});found=[]
    for a,b,c in itertools.combinations(nodes,3):
        ab,bc,ac=matrix.get((a,b)),matrix.get((b,c)),matrix.get((a,c))
        if None not in (ab,bc,ac) and sum(p>=threshold for p in (ab,bc,ac))==2:found.append({"items":[a,b,c],"probabilities":[ab,bc,ac]})
    return found
def _groups(size,judged,threshold,linkage):
    groups=[{i} for i in range(size)]; probs={(min(x["left"],x["right"]),max(x["left"],x["right"])):x["probability"] for x in judged}
    while True:
        best=None
        for i,j in itertools.combinations(range(len(groups)),2):
            values=[probs.get(tuple(sorted((a,b))),0) for a in groups[i] for b in groups[j]];score=min(values) if linkage=="complete" else sum(values)/len(values)
            if score>=threshold and (best is None or score>best[0]):best=(score,i,j)
        if not best:break
        _,i,j=best;groups[i]|=groups.pop(j)
    return [sorted(g) for g in groups]
def dedupe(items,rule,provider=None,*,blocking=None,cache=None,certain_below=.15,certain_above=.9,pack=1,budget_usd=float("inf"),threshold=.5,linkage="complete",existing=None):
    provider=provider or FakeJev();cache=cache if cache is not None else {}
    judged,skipped,cost=_judge(items,rule,provider,blocking or {},cache,certain_below,certain_above,pack,budget_usd)
    return {"groups":_groups(len(items),judged,threshold,linkage),"judged_pairs":judged,"skipped_pairs":skipped,"conflicts":conflicts(judged,threshold),"cost":cost,"cache":cache}
def cluster(*args,**kwargs):return dedupe(*args,**kwargs)
def contradict(items,rule,provider=None,**kwargs):
    result=dedupe(items,rule,provider,**kwargs);result["contradictions"]=[x for x in result["judged_pairs"] if x["probability"]>=kwargs.get("threshold",.5)];return result
def link(left,right,rule,provider=None,**kwargs):
    items=left+right;result=dedupe(items,rule,provider,**kwargs);result["links"]=[x for x in result["judged_pairs"] if x["left"]<len(left)<=x["right"]];return result
