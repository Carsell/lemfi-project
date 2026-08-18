"""Tests for the things that could go wrong quietly."""
import sys
from pathlib import Path
import numpy as np, pandas as pd, pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import generate
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


def test_validator_rejects_orphan_transactions():
    users = pd.DataFrame({"user_id": [1, 2], "home_country": ["NG", "GH"]})
    txns = pd.DataFrame({"transaction_id": [1], "user_id": [99], "amount": [1.0],
                         "exchange_rate": [1.0], "converted_amount": [1.0]})
    with pytest.raises(DataQualityError, match="no user row"):
        check_raw(users, txns)


def test_structuring_is_invisible_at_transaction_grain():
    """The premise of the whole project. Every structured transfer is below the reporting
    threshold, so no single-transaction amount rule can separate them from ordinary traffic."""
    t = pd.read_csv("data/clean/transactions.csv")
    daily = t.groupby(["user_id", "occurred_on"]).agg(
        n=("transaction_id", "count"), total=("amount_gbp", "sum"),
        largest=("amount_gbp", "max")).reset_index()
    hits = daily[(daily.n >= 3) & (daily.largest < 10_000) & (daily.total > 10_000)]
    # Guard against the generator drifting to zero structuring, which would silently turn
    # finding 4 into a claim about nothing. Set well below the current count, not at it.
    assert len(hits) > 20, "no structuring in the data, the generator has drifted"
    assert hits.largest.max() < 10_000


def test_daily_aggregate_reconciles_to_transactions():
    """Mirrors the dbt singular test, so a break shows up in Python too."""
    t = pd.read_csv("data/clean/transactions.csv")
    daily = t.groupby(["user_id", "occurred_on"])["amount_gbp"].sum()
    assert abs(daily.sum() - t.amount_gbp.sum()) < 1
