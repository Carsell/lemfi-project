"""Shared assumptions for the synthetic compliance scenario.

These are scenario choices, not claims about LemFi policy or UK regulation.
Keeping the Python values here prevents the generator, analysis and tests from
quietly using different thresholds.
"""

SCENARIO_THRESHOLD_GBP = 10_000.0
ALERT_AMOUNT_THRESHOLD_GBP = 6_000.0
REVIEWER_DAILY_CAPACITY = 40

