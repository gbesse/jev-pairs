"""Run the same synthetic fixture demo shipped in the installed package."""
import json
from jev_pairs.optimizer_demo import demo

if __name__ == "__main__":
    print(json.dumps(demo(), indent=2, sort_keys=True))
