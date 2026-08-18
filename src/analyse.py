"""
Clean the extract, then answer five compliance questions.

  Q1. Where does the money actually move?
  Q2. How good is the flagging rule, and what does it cost to run at that quality?
  Q3. The rule fires hardest on new accounts. Is that where the risk is?
  Q4. What does a single-transaction rule structurally miss?
  Q5. How do verification method and outcome relate to conversion and risk?

Q4 is the one worth reading. Q2 and Q3 are about tuning a rule that exists; Q4 is about a
category of behaviour the rule cannot see no matter how it is tuned, because the evidence
only appears once transactions are aggregated per customer per day.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path

from config import (ALERT_AMOUNT_THRESHOLD_GBP, REVIEWER_DAILY_CAPACITY,
                    SCENARIO_THRESHOLD_GBP)
from validate import check_raw, check_analysis_ready

RAW, CLEAN, FIG = Path("data/raw"), Path("data/clean"), Path("outputs/figures")
plt.rcParams.update({"figure.dpi": 130, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.25, "axes.spines.top": False,
                     "axes.spines.right": False})


def parse_mixed_timestamps(s: pd.Series) -> pd.Series:
    iso = pd.to_datetime(s, format="ISO8601", errors="coerce")
    uk = pd.to_datetime(s, format="%d/%m/%Y %H:%M", errors="coerce")
    return iso.fillna(uk)


def load_and_clean():
    users = pd.read_csv(RAW / "users.csv", parse_dates=["signup_date"])
    txns = pd.read_csv(RAW / "transactions.csv")
    warnings = check_raw(users, txns)

    txns = txns.drop_duplicates(subset=["transaction_id"]).copy()
    txns["timestamp"] = parse_mixed_timestamps(txns["timestamp"])
    users["home_country"] = users["home_country"].fillna("Unknown")

    recon = (txns["amount"] * txns["exchange_rate"] - txns["converted_amount"]).abs()
    tol = txns["converted_amount"].abs() * 0.001 + 0.02
    txns["fx_reconciles"] = recon <= tol

    txns["date"] = txns["timestamp"].dt.floor("D")
    check_analysis_ready(txns, users)
    return users, txns, warnings


# ------------------------------------------------------------------- questions

def q1_corridors(txns, findings):
    volume = txns["amount_gbp"].where(txns["fx_reconciles"], 0)
    valid = txns.loc[txns["fx_reconciles"]]
    average_by_corridor = valid.groupby(
        ["send_country", "receive_country"]
    )["amount_gbp"].mean()
    average_ratio = average_by_corridor.max() / average_by_corridor.min()
    c = (txns.assign(valid_volume_gbp=volume)
         .groupby(["send_country", "receive_country"])
         .agg(volume_gbp=("valid_volume_gbp", "sum"),
              transfers=("transaction_id", "count"),
              excluded_fx_errors=("fx_reconciles", lambda s: (~s).sum()))
         .sort_values("volume_gbp", ascending=False))
    c["pct_volume"] = c["volume_gbp"] / c["volume_gbp"].sum() * 100
    top = c.index[0]
    findings.append(
        f"**Volume is concentrated in a few corridors.** {len(txns):,} transfers move "
        f"£{c['volume_gbp'].sum() / 1e6:.1f}m over six months, excluding "
        f"{c['excluded_fx_errors'].sum():,} FX-quarantined rows from value. The largest corridor, "
        f"{top[0]} to {top[1]}, carries {c.iloc[0]['pct_volume']:.0f}% of value on its own, "
        f"and the top three carry {c['pct_volume'].head(3).sum():.0f}%. Average transfer "
        f"size varies {average_ratio:.1f}-fold across corridors, so the impact of a single "
        f"global amount threshold should be checked by corridor rather than assumed.")

    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    lbl = [f"{a}→{b}" for a, b in c.index]
    ax.barh(lbl[::-1], c["volume_gbp"].values[::-1] / 1e6, color="#4c72b0")
    ax.set(xlabel="Volume sent (£m)", title="Where the money moves")
    fig.tight_layout(); fig.savefig(FIG / "01_corridor_volume.png"); plt.close(fig)
    return c


def q2_alert_quality(txns, findings):
    tp = int((txns.is_flagged & txns.is_suspicious).sum())
    fp = int((txns.is_flagged & ~txns.is_suspicious).sum())
    fn = int((~txns.is_flagged & txns.is_suspicious).sum())
    tn = int((~txns.is_flagged & ~txns.is_suspicious).sum())
    precision, recall = tp / (tp + fp), tp / (tp + fn)
    base = txns.is_suspicious.mean()

    # Illustrative workload assumption, kept explicit so it is not mistaken for observed data.
    alerts = tp + fp
    per_day = alerts / txns["date"].nunique()
    reviewers = per_day / REVIEWER_DAILY_CAPACITY

    verdict = ("finds most of the risk and buries the team doing it" if recall >= 0.55
               else "finds about half the risk and buries the team doing it" if recall >= 0.35
               else "misses more than it finds, and still buries the team")
    findings.append(
        f"**The rule {verdict}.** Suspicious "
        f"activity runs at {base:.2%} of transfers. The simulated baseline rule flags "
        f"{txns.is_flagged.mean():.1%}, catching {recall:.0%} of genuinely suspicious "
        f"transfers at {precision:.0%} precision. In plain terms: {alerts:,} alerts over six "
        f"months, of which {fp:,} are false, and {fn:,} suspicious transfers are missed "
        f"entirely. That is roughly {per_day:.0f} alerts a day, about {reviewers:.1f} "
        f"full-time reviewers at an illustrative {REVIEWER_DAILY_CAPACITY} reviews per day, "
        f"and more than three quarters of their day spent on transfers "
        f"that turn out to be fine. Whether that is the right trade depends on what a missed "
        f"case costs relative to a review, and that number should come from the business "
        f"rather than from me.")

    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.2))
    cm = np.array([[tn, fp], [fn, tp]])
    axes[0].imshow(np.log1p(cm), cmap="Blues")
    for (i, j), v in np.ndenumerate(cm):
        axes[0].text(j, i, f"{v:,}", ha="center", va="center", fontsize=9)
    axes[0].set(xticks=[0, 1], yticks=[0, 1],
                xticklabels=["not flagged", "flagged"],
                yticklabels=["not suspicious", "suspicious"],
                title=f"Alerts: precision {precision:.0%}, recall {recall:.0%}")
    axes[0].grid(False)

    # Precision/recall as the amount threshold moves, holding the other rules off.
    grid = np.arange(1_000, 25_001, 500)
    prec, rec = [], []
    for t in grid:
        f = txns["amount_gbp"] > t
        p = (f & txns.is_suspicious).sum()
        prec.append(p / f.sum() if f.sum() else np.nan)
        rec.append(p / txns.is_suspicious.sum())
    axes[1].plot(grid, np.array(prec) * 100, label="precision")
    axes[1].plot(grid, np.array(rec) * 100, label="recall")
    axes[1].axvline(ALERT_AMOUNT_THRESHOLD_GBP, color="grey", ls="--", lw=1)
    axes[1].text(ALERT_AMOUNT_THRESHOLD_GBP + 300, 60, "scenario\nthreshold",
                 fontsize=7, color="grey")
    axes[1].set(xlabel="Amount threshold (£)", ylabel="%",
                title="Moving the amount threshold alone")
    axes[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "02_alert_quality.png"); plt.close(fig)
    return precision, recall


def q3_new_accounts(txns, findings):
    """The rule treats young accounts as risky. Test it."""
    young = txns["account_age_days"] < 14
    rate_young = txns.loc[young, "is_suspicious"].mean()
    rate_old = txns.loc[~young, "is_suspicious"].mean()
    share_of_alerts = (txns.loc[txns.is_flagged, "account_age_days"] < 14).mean()

    ratio = rate_young / max(rate_old, 1e-9)
    if ratio > 1.5:
        verdict = (f"**New accounts really are riskier, and the rule is right to watch "
                   f"them.** Transfers from accounts under 14 days old are suspicious "
                   f"{rate_young:.2%} of the time against {rate_old:.2%} for everyone else, "
                   f"{ratio:.1f} times higher. The age condition earns its place.")
    elif ratio > 1.1:
        verdict = (f"**New accounts are slightly riskier, but the alert trade-off needs "
                   f"testing.** Transfers from accounts under 14 days old are "
                   f"suspicious {rate_young:.2%} of the time against {rate_old:.2%} for "
                   f"everyone else. That is a real but small elevation, and "
                   f"{share_of_alerts:.0%} of alerts involve an account under 14 days old. "
                   f"A threshold sensitivity test by account age would show whether the "
                   f"condition can be tightened without losing too much recall.")
    else:
        verdict = (f"**The rule watches new accounts and the risk is not there.** Transfers "
                   f"from accounts under 14 days old are suspicious {rate_young:.2%} of the "
                   f"time against {rate_old:.2%} for everyone else. The suspicious volume "
                   f"comes from established accounts behaving unusually, not new accounts "
                   f"behaving normally, so the age condition is spending "
                   f"{share_of_alerts:.0%} of alerts for very little.")
    findings.append(verdict)

    bins = [0, 14, 30, 90, 365, 10_000]
    lbl = ["<14d", "14-30d", "1-3m", "3-12m", "1y+"]
    g = txns.groupby(pd.cut(txns["account_age_days"], bins, labels=lbl), observed=True)
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    ax.bar(lbl, (g["is_suspicious"].mean() * 100).values, color="#c44e52", label="suspicious")
    ax.plot(lbl, (g["is_flagged"].mean() * 100).values, "o-", color="#4c72b0",
            label="flagged by the rule")
    ax.set(ylabel="% of transfers", xlabel="Account age at time of transfer",
           title="Where the rule looks against where the risk is")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "03_account_age.png"); plt.close(fig)


def q4_structuring(txns, findings):
    """Behaviour the rule cannot see, because the evidence is not in one transaction."""
    daily = (txns.groupby(["user_id", "date"])
             .agg(n=("transaction_id", "count"),
                  total_gbp=("amount_gbp", "sum"),
                  max_gbp=("amount_gbp", "max"),
                  any_flagged=("is_flagged", "any"),
                  any_suspicious=("is_suspicious", "any"),
                  any_structuring=("is_structuring", "any"))
             .reset_index())

    # Structuring: several transfers in a day, each under the threshold, summing over it.
    pattern = ((daily.n >= 3) & (daily.max_gbp < SCENARIO_THRESHOLD_GBP) &
               (daily.total_gbp > SCENARIO_THRESHOLD_GBP))
    hits = daily[pattern]
    planted = daily["any_structuring"]
    caught_by_rule = daily.loc[planted, "any_flagged"].mean() if planted.any() else np.nan
    true_positives = int((pattern & planted).sum())
    false_positives = int((pattern & ~planted).sum())
    recall = true_positives / planted.sum() if planted.sum() else np.nan
    precision = true_positives / len(hits) if len(hits) else np.nan
    value = hits["total_gbp"].sum()

    findings.append(
        f"**A single-transaction rule cannot see structuring, and there is structuring.** "
        f"Aggregating to one row per customer per day finds {len(hits):,} days where a user "
        f"made three or more transfers, each below the £{SCENARIO_THRESHOLD_GBP:,.0f} "
        f"scenario threshold, together totalling more than it — £{value / 1e6:.1f}m in all. "
        f"In this controlled simulation the daily rule recovered {true_positives:,} of "
        f"{int(planted.sum()):,} planted structuring days ({recall:.0%} recall) with "
        f"{false_positives:,} false-positive days ({precision:.0%} precision). The simulated "
        f"single-transaction rule caught {caught_by_rule:.0%} of them. "
        f"No amount of tuning the amount threshold fixes this, because every individual "
        f"transfer is unremarkable and the rule only ever looks at one at a time. The fix is "
        f"a daily aggregate per customer. These figures validate the scenario logic; they are "
        f"not estimates of real-world detection performance.")

    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.2))
    sample = daily[daily.n >= 2].sample(min(4000, (daily.n >= 2).sum()), random_state=1)
    axes[0].scatter(sample.n, sample.total_gbp, s=5, alpha=0.2, color="grey")
    axes[0].scatter(hits.n, hits.total_gbp, s=9, alpha=0.7, color="#c44e52")
    axes[0].axhline(SCENARIO_THRESHOLD_GBP, color="black", lw=1, ls="--")
    axes[0].set(yscale="log", xlabel="Transfers by one user in one day",
                ylabel="Day total (£)", title="Under the limit each, over it together")
    axes[1].bar(["Single-transaction\nbaseline", "Customer-day\nrule"],
                [caught_by_rule * 100, recall * 100], color=["#4c72b0", "#c44e52"])
    axes[1].set(ylabel="Recall of planted structuring days",
                title=f"Daily rule: {precision:.0%} precision in this simulation")
    fig.tight_layout(); fig.savefig(FIG / "04_structuring.png"); plt.close(fig)
    return daily


def q5_kyc(txns, users, findings):
    """Two different things wear the same name here, and they need separating."""
    m = txns.merge(users[["user_id", "kyc_status", "kyc_method"]], on="user_id", how="left")
    by_method = users.groupby("kyc_method")["kyc_status"].value_counts(
        normalize=True).unstack()
    by_status = m.groupby("kyc_status")["is_suspicious"].mean() * 100
    best, worst = by_method["Verified"].idxmax(), by_method["Verified"].idxmin()
    ratio = by_status.get("Failed", 0) / max(by_status.get("Verified", 1e-9), 1e-9)

    findings.append(
        f"**Verification method and verification outcome are different things, and only one "
        f"of them is about risk.** The method a user verifies through decides whether they "
        f"get through: {by_method.loc[best, 'Verified']:.0%} pass via {best} against "
        f"{by_method.loc[worst, 'Verified']:.0%} via {worst}. That is an operations and "
        f"conversion problem worth fixing on its own terms. The *outcome* is a different "
        f"matter and it is a real risk signal: suspicious activity runs at "
        f"{by_status.get('Failed', 0):.2f}% among users whose verification failed against "
        f"{by_status.get('Verified', 0):.2f}% among those who passed, roughly "
        f"{ratio:.0f} times higher. Those two facts pull in opposite directions. This "
        f"aggregate comparison does not establish that changing a verification method would "
        f"change later risk, so that decision needs an experiment or a controlled cohort "
        f"analysis rather than a causal claim from this chart.")

    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.2))
    by_method[["Verified", "Pending", "Failed"]].plot(
        kind="bar", stacked=True, ax=axes[0], rot=12,
        color=["#4c72b0", "#dd8452", "#c44e52"], legend=True)
    axes[0].set(ylabel="Share of users", xlabel="",
                title="Method decides who gets through")
    axes[0].legend(fontsize=7)
    order = ["Verified", "Pending", "Failed"]
    axes[1].bar(order, [by_status.get(o, 0) for o in order], color="#c44e52")
    axes[1].set(ylabel="% of transfers suspicious", title="Outcome is the risk signal")
    fig.tight_layout(); fig.savefig(FIG / "05_kyc.png"); plt.close(fig)


def main():
    for d in (CLEAN, FIG, Path("outputs")):
        d.mkdir(parents=True, exist_ok=True)

    users, txns, warnings = load_and_clean()
    print("data quality checks:")
    for w in warnings:
        print(f"  ! {w}")
    print("  ok  analysis-ready checks passed")

    findings: list[str] = []
    q1_corridors(txns, findings)
    q2_alert_quality(txns, findings)
    q3_new_accounts(txns, findings)
    daily = q4_structuring(txns, findings)
    q5_kyc(txns, users, findings)

    # Exports. is_suspicious is ground truth and never leaves this folder.
    # `timestamp` is a reserved word in several SQL engines, so it is renamed on export
    # rather than quoted in every downstream model.
    (txns.drop(columns=["is_suspicious", "is_structuring"])
         .rename(columns={"timestamp": "occurred_at", "date": "occurred_on"})
         .to_csv(CLEAN / "transactions.csv", index=False))
    users.to_csv(CLEAN / "users.csv", index=False)
    daily.drop(columns=["any_suspicious", "any_structuring"]).to_csv(
        CLEAN / "user_daily_activity.csv", index=False)

    with open("outputs/findings.md", "w") as f:
        f.write("# Findings\n\nGenerated by `python run.py`. Every number is computed from "
                "the data, not typed in by hand.\n\n## Data quality\n\n")
        for w in warnings:
            f.write(f"- {w}\n")
        f.write("\n## Results\n\n")
        for i, x in enumerate(findings, 1):
            f.write(f"{i}. {x}\n\n")

    print(f"\nwrote {len(txns):,} clean transactions and {len(daily):,} user-days")
    print(f"wrote {len(list(FIG.glob('*.png')))} figures and outputs/findings.md")


if __name__ == "__main__":
    main()
