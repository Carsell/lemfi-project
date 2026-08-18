"""
Simulate remittance transactions, users, and an imperfect compliance flagging rule.

Why this file was rewritten
---------------------------
The first version of this project produced 500,000 transactions that all carried the same
date, and an `is_flagged` column that was a 4% coin flip. It correlated 0.00 with the user's
risk score and -0.0008 with the transaction amount, and the flag rate was between 3.9% and
4.1% in every country, every transaction type and every KYC status.

Two consequences. The dbt marts grouped by month, so with one date they returned a single
row each and no time series existed. And there was nothing to analyse: any pattern found in
flags like that is noise, and it would be different noise on the next run.

The generator now builds a world with structure, and this docstring states what that
structure is. Recovering it is method. Recovering something else is an artefact.

What is deliberately built in
-----------------------------
1. **Corridors.** Three send countries and four receive countries, with different volumes,
   average amounts and underlying risk. Corridor is a real driver, not a label.
2. **A latent `is_suspicious` flag that no downstream model sees.** This is the ground truth
   the compliance function is trying to find. It rises with new accounts, unusual amounts
   relative to the user's own history, high-risk corridors, and structuring.
3. **Structuring.** A small set of users deliberately split large sums into several
   transfers below the £10,000 synthetic scenario threshold, within a single day. Every
   individual transfer looks ordinary. Only a per-user, per-day aggregate reveals it.
4. **A rules-based flag that is imperfect on purpose.** `is_flagged` fires on simple
   single-transaction conditions: a large amount, a high-risk corridor, an unverified user,
   a brand new account. It therefore misses structuring entirely and fires on plenty of
   innocent large transfers. The gap between `is_flagged` and `is_suspicious` is the point of
   the whole analysis.
5. **Time.** Six months of activity, so growth, seasonality and cohort behaviour exist.

Deliberate data quality problems
--------------------------------
  * a replayed batch of duplicated transactions
  * timestamps written in two different formats
  * a small number of exchange rates corrupted so amount x rate no longer reconciles
  * some users with a missing country

`validate.py` finds these. `analyse.py` handles them. Both say what they did.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from config import ALERT_AMOUNT_THRESHOLD_GBP, SCENARIO_THRESHOLD_GBP

SEED = 11
N_USERS = 10_000
N_MONTHS = 6
START = pd.Timestamp("2025-01-01")
END = START + pd.DateOffset(months=N_MONTHS)
# Corridors the simulated baseline rule does not treat as high risk. Structuring goes here.
QUIET_CORRIDORS = [("UK", "NG"), ("UK", "GH"), ("UK", "KE"), ("CA", "GH")]

# corridor: (share of volume, mean amount, latent risk multiplier)
CORRIDORS = {
    ("UK", "NG"): (0.30, 620, 1.00),
    ("US", "NG"): (0.14, 780, 1.35),
    ("UK", "GH"): (0.13, 540, 0.85),
    ("CA", "GH"): (0.07, 610, 0.90),
    ("UK", "KE"): (0.12, 480, 0.80),
    ("US", "KE"): (0.08, 700, 1.20),
    ("US", "UG"): (0.09, 660, 1.55),
    ("CA", "UG"): (0.07, 590, 1.10),
}
CURRENCY = {"NG": "NGN", "GH": "GHS", "KE": "KES", "UG": "UGX",
            "UK": "GBP", "US": "USD", "CA": "CAD"}
# Approximate GBP value of one unit. The rates are fixed scenario inputs, not live FX.
GBP_PER_UNIT = {"GBP": 1.0, "USD": 1 / 1.27, "CAD": 1 / 1.72,
                "NGN": 0.00052, "GHS": 0.064, "KES": 0.0061, "UGX": 0.00021}
TXN_TYPES = ["Send Money", "Wallet Top-Up", "Bill Payment", "Bank Withdrawal"]
KYC_METHODS = ["Document Upload", "Bank Verification", "Utility Bill"]


def build_users(rng):
    signup = START - pd.to_timedelta(rng.integers(-170, 400, N_USERS), unit="D")
    method = rng.choice(KYC_METHODS, N_USERS, p=[0.42, 0.34, 0.24])

    # Verification success depends on the method. Document upload works best; utility bills
    # fail most often, which is a real and boring operational fact rather than a risk signal.
    p_verified = pd.Series(method).map(
        {"Document Upload": 0.82, "Bank Verification": 0.76, "Utility Bill": 0.55}).values
    draw = rng.random(N_USERS)
    status = np.where(draw < p_verified, "Verified",
                      np.where(draw < p_verified + 0.14, "Pending", "Failed"))

    # Latent propensity to transact suspiciously. Most users are fine.
    base = rng.beta(1.1, 130.0, N_USERS)
    base = np.where(status == "Failed", base * 2.6, base)
    base = np.where(status == "Pending", base * 1.4, base)

    return pd.DataFrame({
        "user_id": np.arange(1, N_USERS + 1),
        "signup_date": signup,
        "home_country": rng.choice(["UK", "US", "CA"], N_USERS, p=[0.50, 0.30, 0.20]),
        "kyc_status": status,
        "kyc_method": method,
        "suspicion_propensity_hidden": np.round(base, 5),
    })


def build_transactions(users, rng):
    corridors = list(CORRIDORS)
    weights = np.array([CORRIDORS[c][0] for c in corridors])
    weights = weights / weights.sum()

    # Activity per user over the window. Heavy tail, as real remittance usage is.
    n_txn = rng.poisson(rng.gamma(1.5, 5.0, len(users))).clip(0, 200)
    total = int(n_txn.sum())
    user_idx = np.repeat(np.arange(len(users)), n_txn)

    ci = rng.choice(len(corridors), total, p=weights)
    send = np.array([corridors[i][0] for i in ci])
    recv = np.array([corridors[i][1] for i in ci])
    risk_mult = np.array([CORRIDORS[corridors[i]][2] for i in ci])
    mean_amt = np.array([CORRIDORS[corridors[i]][1] for i in ci])

    # Transactions can only occur after the customer signs up. Generating dates across the
    # full window and clipping negative account ages would turn impossible pre-signup rows
    # into apparently new accounts and corrupt the tenure analysis.
    signup_for_txn = pd.Series(users["signup_date"].values[user_idx])
    eligible_start = signup_for_txn.clip(lower=START)
    available_minutes = ((END - eligible_start) / pd.Timedelta(minutes=1)).astype(int)
    offsets = (rng.random(total) * available_minutes).astype(int)
    ts = eligible_start + pd.to_timedelta(offsets, unit="m")

    amount_gbp = np.round(rng.lognormal(np.log(mean_amt), 0.85), 2)

    df = pd.DataFrame({
        "user_id": users["user_id"].values[user_idx],
        "timestamp": ts,
        "send_country": send,
        "receive_country": recv,
        "amount_gbp": amount_gbp,
        "transaction_type": rng.choice(TXN_TYPES, total, p=[0.42, 0.24, 0.19, 0.15]),
        "device": rng.choice(["Mobile", "Web"], total, p=[0.71, 0.29]),
        "_risk_mult": risk_mult,
        "_prop": users["suspicion_propensity_hidden"].values[user_idx],
        "_signup": users["signup_date"].values[user_idx],
    })

    df["account_age_days"] = (
        df["timestamp"] - pd.to_datetime(df["_signup"])).dt.days
    df["is_structuring"] = False

    # ---- ground truth: which transactions are genuinely suspicious -------------
    # New accounts, high-risk corridors and amounts far above the user's own norm.
    user_median = df.groupby("user_id")["amount_gbp"].transform("median")
    amount_ratio = df["amount_gbp"] / user_median.clip(lower=1)
    # Absolute size matters as well as size relative to the user's own norm. Without this
    # term, large transfers are no more likely to be suspicious than small ones, which makes
    # the simulated rule's amount condition meaningless by construction and hands the
    # analysis a rule that fails for the wrong reason.
    p = (df["_prop"]
         * df["_risk_mult"]
         * np.where(df["account_age_days"] < 30, 2.2, 1.0)
         * np.clip(amount_ratio / 3.0, 0.5, 3.0)
         * np.clip(df["amount_gbp"] / 1_500.0, 0.4, 9.0))
    df["is_suspicious"] = rng.random(len(df)) < np.clip(p, 0, 0.9)

    return df.drop(columns=["_risk_mult", "_prop", "_signup"])


def add_structuring(df, users, rng):
    """A few users split a large sum into several transfers under the threshold, same day.

    Each individual transfer is unremarkable. Only a per-user per-day total gives it away,
    which is exactly why a single-transaction rule cannot catch it.
    """
    candidates = users.loc[
        (users.suspicion_propensity_hidden >
         users.suspicion_propensity_hidden.quantile(0.97)) &
        (users.signup_date <= END - pd.Timedelta(days=45)),
        "user_id",
    ]
    chosen = rng.choice(candidates.values, size=12, replace=False)
    rows = []
    for uid in chosen:
        for _ in range(int(rng.integers(1, 4))):          # 1-3 structuring episodes each
            corridor = QUIET_CORRIDORS[int(rng.integers(0, len(QUIET_CORRIDORS)))]
            signup = pd.Timestamp(users.loc[users.user_id.eq(uid), "signup_date"].iloc[0])
            first_day = max(START, signup.normalize() + pd.Timedelta(days=40))
            day = first_day + pd.Timedelta(
                days=int(rng.integers(0, max((END - first_day).days, 1))))
            n = int(rng.integers(5, 9))
            for k in range(n):
                rows.append(dict(
                    user_id=uid,
                    timestamp=day + pd.Timedelta(hours=int(rng.integers(7, 22)),
                                                 minutes=int(rng.integers(0, 60))),
                    # Deliberately not a corridor watched by the simulated baseline rule:
                    # route they know is watched, which is exactly why the corridor rule
                    # never sees them.
                    send_country=corridor[0], receive_country=corridor[1],
                    # Each transfer also sits below the alert amount condition, so the
                    # single-transaction baseline cannot detect the planted episode.
                    amount_gbp=float(np.round(rng.uniform(2_200, 5_400), 2)),
                    transaction_type="Send Money",
                    device=rng.choice(["Mobile", "Web"]),
                    account_age_days=(day - signup.normalize()).days,
                    is_suspicious=True,
                    is_structuring=True,
                ))
    extra = pd.DataFrame(rows)
    assert extra["amount_gbp"].lt(SCENARIO_THRESHOLD_GBP).all()
    return pd.concat([df, extra], ignore_index=True)


def apply_flagging_rule(df):
    """A simulated baseline compliance rule. Simple, single-transaction, imperfect.

    It fires on: a large amount, a high-risk corridor with an above-average amount, or a
    brand new account moving real money. Every condition looks at one transaction in
    isolation, which is why structuring walks straight through it.
    """
    large = df["amount_gbp"] > ALERT_AMOUNT_THRESHOLD_GBP
    risky_corridor = (df["send_country"].eq("US") &
                      df["receive_country"].isin(["NG", "UG"]) &
                      (df["amount_gbp"] > 1_800))
    new_account = (df["account_age_days"] < 14) & (df["amount_gbp"] > 4_000)
    df["is_flagged"] = large | risky_corridor | new_account
    return df


def finalise(df, rng):
    send_ccy = df["send_country"].map(CURRENCY)
    recv_ccy = df["receive_country"].map(CURRENCY)
    send_gbp = send_ccy.map(GBP_PER_UNIT)
    receive_gbp = recv_ccy.map(GBP_PER_UNIT)
    df["send_currency"] = send_ccy
    df["receive_currency"] = recv_ccy
    df["amount"] = np.round(df["amount_gbp"] / send_gbp, 2)          # local currency sent
    df["exchange_rate"] = np.round(send_gbp / receive_gbp, 8)
    df["converted_amount"] = np.round(df["amount"] * df["exchange_rate"], 2)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df.insert(0, "transaction_id", np.arange(1, len(df) + 1))
    return df


def plant_defects(users, txns, rng):
    notes = []

    idx = users.sample(40, random_state=SEED).index
    users.loc[idx, "home_country"] = np.nan
    notes.append(f"blanked home_country on {len(idx)} users")

    bad = txns.sample(150, random_state=SEED).index
    txns.loc[bad, "exchange_rate"] = np.round(
        txns.loc[bad, "exchange_rate"] * rng.uniform(1.5, 4.0, len(bad)), 8)
    notes.append(f"corrupted {len(bad)} exchange rates so amount x rate no longer "
                 f"reconciles to converted_amount")

    # Duplicate only rows outside the FX quarantine, so the raw and clean defect counts agree.
    dupes = txns.drop(index=bad).sample(600, random_state=SEED)
    txns = pd.concat([txns, dupes], ignore_index=True)
    notes.append(f"duplicated {len(dupes)} transactions (a replayed settlement batch)")

    txns["timestamp"] = txns["timestamp"].astype(str)
    flip = txns.sample(4_000, random_state=SEED).index
    txns.loc[flip, "timestamp"] = pd.to_datetime(
        txns.loc[flip, "timestamp"]).dt.strftime("%d/%m/%Y %H:%M")
    notes.append(f"wrote {len(flip)} timestamps in dd/mm/yyyy instead of ISO")

    return users, txns, notes


def main(out_dir="data/raw"):
    rng = np.random.default_rng(SEED)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    users = build_users(rng)
    txns = build_transactions(users, rng)
    txns = add_structuring(txns, users, rng)
    txns = apply_flagging_rule(txns)
    txns = finalise(txns, rng)
    users, txns, notes = plant_defects(users, txns, rng)

    cols = ["transaction_id", "user_id", "timestamp", "send_country", "receive_country",
            "send_currency", "receive_currency", "amount", "converted_amount",
            "exchange_rate", "amount_gbp", "transaction_type", "device",
            "account_age_days", "is_flagged", "is_suspicious", "is_structuring"]
    txns[cols].to_csv(out / "transactions.csv", index=False)
    users.drop(columns=["suspicion_propensity_hidden"]).to_csv(
        out / "users.csv", index=False)

    print(f"wrote {len(users):,} users and {len(txns):,} transactions to {out}/")
    print(f"  flagged by the rule : {txns.is_flagged.mean():.2%}")
    print(f"  genuinely suspicious: {txns.is_suspicious.mean():.2%}")
    print("planted data quality problems:")
    for n in notes:
        print(f"  - {n}")


if __name__ == "__main__":
    main()
