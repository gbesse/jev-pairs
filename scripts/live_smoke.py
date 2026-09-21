# Purpose: Guard the currently unwired opt-in live path from accidental paid use.
import os
if not os.getenv("TYPESAFE_API_KEY"): raise SystemExit("Set TYPESAFE_API_KEY")
raise SystemExit("Live smoke is intentionally not wired in this alpha; use a reviewed provider adapter")
