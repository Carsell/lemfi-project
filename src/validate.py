"""
Data quality checks on the raw extract.

Warnings are defects the pipeline is expected to handle: duplicates, missing countries,
mixed date formats. They get counted and reported.

Failures mean the analysis would be wrong and nobody would notice: an empty table, a
transaction belonging to a user who does not exist, a duplicated primary key that survives
cleaning. They raise.

The distinction matters because a check that only ever prints is a check nobody reads.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class DataQualityError(Exception):
    pass


def check_raw(users: pd.DataFrame, txns: pd.DataFrame) -> list[str]:
    warnings, failures = [], []

    for name, df in [("users", users), ("transactions", txns)]:
        if df.empty:
            failures.append(f"{name} is empty")

    if users["user_id"].duplicated().any():
        failures.append(f"{users['user_id'].duplicated().sum()} duplicate user_id")

    orphans = (~txns["user_id"].isin(users["user_id"])).sum()
    if orphans:
        failures.append(f"{orphans} transactions reference a user_id with no user row")

    if failures:
        raise DataQualityError("; ".join(failures))

    dup_txn = txns["transaction_id"].duplicated().sum()
    if dup_txn:
        warnings.append(
            f"{dup_txn:,} duplicate transaction_id — deduplicated on load. Left in place "
            f"they would inflate corridor volume and double-count alerts")

    missing_country = users["home_country"].isna().sum()
    if missing_country:
        warnings.append(f"{missing_country} users with no home_country — kept as 'Unknown'")

    # amount x exchange_rate should reconcile to converted_amount. Where it does not, the
    # rate is wrong, and a corridor volume built on it would be quietly wrong too.
    recon = (txns["amount"] * txns["exchange_rate"] - txns["converted_amount"]).abs()
    tol = txns["converted_amount"].abs() * 0.001 + 0.02
    broken = int((recon > tol).sum())
    if broken:
        warnings.append(
            f"{broken} transactions where amount x exchange_rate does not reconcile to "
            f"converted_amount — quarantined, not corrected, because we do not know which "
            f"of the three fields is the wrong one")

    return warnings


def check_analysis_ready(txns: pd.DataFrame, users: pd.DataFrame) -> None:
    failures = []

    if txns["transaction_id"].duplicated().any():
        failures.append("duplicate transaction_id survived cleaning")

    if txns["timestamp"].isna().any():
        failures.append(f"{txns['timestamp'].isna().sum()} timestamps failed to parse")

    if (txns["amount_gbp"] < 0).any():
        failures.append("negative transaction amounts")

    temporal = txns[["transaction_id", "user_id", "timestamp"]].merge(
        users[["user_id", "signup_date"]], on="user_id", how="left", validate="many_to_one"
    )
    before_signup = temporal["timestamp"] < temporal["signup_date"] - pd.Timedelta(days=1)
    if before_signup.any():
        failures.append(f"{before_signup.sum()} transactions occur before user signup")

    if failures:
        raise DataQualityError("; ".join(failures))
