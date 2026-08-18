"""Tests for the things that could go wrong quietly."""
import sys
from pathlib import Path
import numpy as np, pandas as pd, pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import generate
import config
from validate import check_raw, check_analysis_ready, DataQualityError


def test_generation_is_reproducible():
    a = generate.build_users(np.random.default_rng(generate.SEED))
    b = generate.build_users(np.random.default_rng(generate.SEED))
    pd.testing.assert_frame_equal(a, b)


def test_ground_truth_never_reaches_the_clean_extract():
    """is_suspicious does not exist in production. A model trained on it would score
    perfectly and be worthless, so it must not survive the export."""
    clean = pd.read_csv("data/clean/transactions.csv", nrows=5)
    assert "is_suspicious" not in clean.columns
    assert "is_structuring" not in clean.columns


def test_no_transactions_before_signup():
    users = pd.read_csv("data/clean/users.csv", parse_dates=["signup_date"])
    txns = pd.read_csv("data/clean/transactions.csv", parse_dates=["occurred_at"])
    joined = txns[["transaction_id", "user_id", "occurred_at"]].merge(
        users[["user_id", "signup_date"]], on="user_id", validate="many_to_one"
    )
    assert not (joined["occurred_at"] < joined["signup_date"] - pd.Timedelta(days=1)).any()


def test_validator_rejects_orphan_transactions():
    users = pd.DataFrame({"user_id": [1, 2], "home_country": ["NG", "GH"]})
    txns = pd.DataFrame({"transaction_id": [1], "user_id": [99], "amount": [1.0],
                         "exchange_rate": [1.0], "converted_amount": [1.0]})
    with pytest.raises(DataQualityError, match="no user row"):
        check_raw(users, txns)


def test_structuring_is_invisible_at_transaction_grain():
    """The premise of the whole project. Every candidate transfer is below the synthetic
    scenario threshold, so its pattern only appears at the customer-day grain."""
    t = pd.read_csv("data/clean/transactions.csv")
    daily = t.groupby(["user_id", "occurred_on"]).agg(
        n=("transaction_id", "count"), total=("amount_gbp", "sum"),
        largest=("amount_gbp", "max")).reset_index()
    threshold = config.SCENARIO_THRESHOLD_GBP
    hits = daily[(daily.n >= 3) & (daily.largest < threshold) &
                 (daily.total > threshold)]
    # Guard against the generator drifting to zero structuring, which would silently turn
    # finding 4 into a claim about nothing. Set well below the current count, not at it.
    assert len(hits) > 20, "no structuring in the data, the generator has drifted"
    assert hits.largest.max() < threshold


def test_daily_aggregate_reconciles_to_transactions():
    """Mirrors the dbt singular test, so a break shows up in Python too."""
    t = pd.read_csv("data/clean/transactions.csv")
    daily = t.groupby(["user_id", "occurred_on"])["amount_gbp"].sum()
    assert abs(daily.sum() - t.amount_gbp.sum()) < 1


def test_dbt_threshold_matches_python_scenario():
    """The Python and dbt layers intentionally mirror one scenario value; test the mirror."""
    import re
    project = Path("dbt/lemfi_analytics/dbt_project.yml").read_text()
    match = re.search(r"scenario_threshold:\s*([0-9.]+)", project)
    assert match, "dbt scenario_threshold var is missing"
    assert float(match.group(1)) == config.SCENARIO_THRESHOLD_GBP
