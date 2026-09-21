# Purpose: JSON CLI for estimating and running pairwise operations.
import argparse,json,sys
from pathlib import Path
from .core import estimate,dedupe,cluster,contradict,FakeJev

def main(argv=None):
    p=argparse.ArgumentParser(prog="jev-pairs");p.add_argument("command",choices=["estimate","dedupe","cluster","contradict"]);p.add_argument("input");p.add_argument("--rule",required=True);p.add_argument("--out");p.add_argument("--fake");p.add_argument("--pack",type=int,default=1);p.add_argument("--budget-usd",type=float,default=float("inf"));a=p.parse_args(argv)
    try:
        items=json.loads(Path(a.input).read_text());rule=json.loads(Path(a.rule).read_text())
        if a.command=="estimate":result=estimate(items,rule)
        else:
            fixtures=json.loads(Path(a.fake).read_text()) if a.fake else {};operations={"dedupe":dedupe,"cluster":cluster,"contradict":contradict};result=operations[a.command](items,rule,FakeJev(fixtures),pack=a.pack,budget_usd=a.budget_usd);result.pop("cache",None)
        text=json.dumps(result,indent=2);Path(a.out).write_text(text) if a.out else print(text)
    except Exception as error:print(f"jev-pairs: {error}",file=sys.stderr);raise SystemExit(1)
