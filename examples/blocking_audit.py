"""Compare blocking cost and labeled-match loss on a synthetic catalog."""
import json

from jev_pairs import blocking_report, estimate

RULE = {"id": "catalog", "version": "1", "statement": "Same product", "true": {}, "false": {}, "key_fields": ["name"]}
ITEMS = [
    {"id": "a", "name": "Red running shoe"},
    {"id": "b", "name": "Running shoe, red"},
    {"id": "c", "name": "Blue winter coat"},
    {"id": "d", "name": "Winter coat blue"},
    {"id": "e", "name": "Desk lamp"},
]
# Synthetic human labels, expressed as zero-based fixture indexes.
KNOWN_MATCHES = [(0, 1), (2, 3)]


def audit():
    strategies = {
        "all_pairs": {},
        "shared_token": {"token_overlap": 0.25},
        "exact_name": {"exact_key": True},
    }
    return {
        "source": "synthetic fixture; no Jev calls or measured quality claim",
        "item_count": len(ITEMS),
        "known_matches": len(KNOWN_MATCHES),
        "strategies": {
            name: {
                **blocking_report(ITEMS, RULE, config, KNOWN_MATCHES),
                "estimated_input_tokens": estimate(ITEMS, RULE, config)["estimated_input_tokens"],
            }
            for name, config in strategies.items()
        },
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
