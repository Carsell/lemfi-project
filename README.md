# Remittance Compliance Analytics

Transaction monitoring for a cross-border payments business, built on simulated data. Five
questions a compliance analytics team gets asked, and a dbt layer that models the data at the
grain where the interesting one becomes answerable.

```bash
pip install -r requirements.txt
python run.py
```

That generates the data, runs the quality checks, produces the analysis and charts, and
writes `outputs/findings.md`. The dbt layer reads the same cleaned CSVs directly.

Every number in this README is produced by that command. Nothing is typed in by hand.

> **Portfolio project on synthetic data.** I built it to work through the analytics a
> remittance business actually needs. I have not worked for LemFi and no real customer data
> is involved. The generator plants known structure and documents what it planted, which is
> the only way a finding on simulated data means anything.

---

## What I found

### 1. Volume is concentrated in a few corridors

**75,756** transfers move **£68.6m** over six months. NG→UK alone carries **30%** of value and
the top three corridors carry **59%**. Average transfer size varies more than three-fold
between corridors, so one global monitoring threshold is far too loose in one place and far
too tight in another.

![Corridor volume](outputs/figures/01_corridor_volume.png)

### 2. The rule misses more than it finds, and still buries the team

Suspicious activity runs at **1.09%** of transfers. The production rule flags **3.8%**,
catching **25%** of genuinely suspicious transfers at **7%** precision.

In plain terms: **2,879 alerts** over six months, **2,672 of them false**, and **622**
suspicious transfers missed entirely. That is roughly **16 alerts a day**, about **0.4** of a
full-time reviewer, spending more than three quarters of that time on transfers that turn out
to be fine.

![Alert quality](outputs/figures/02_alert_quality.png)

A high false positive rate is normal in this work — rules-based transaction monitoring
routinely runs above 90% false positives, so 7% precision is unremarkable. The recall is the
problem. Three quarters of suspicious activity never generates an alert at all, and finding 4
explains most of why.

Whether the trade is right depends on what a missed case costs against what a review costs.
That number belongs to the business, not to the analyst, and the threshold chart is drawn so
someone can put their own number against it.

### 3. New accounts are slightly riskier, and not by enough to justify the alert volume

Transfers from accounts under 14 days old are suspicious **1.23%** of the time against
**1.07%** for everyone else. That elevation is real but small, and the rule spends **19%** of
its alerts chasing it.

![Account age](outputs/figures/03_account_age.png)

New-account monitoring is a sound instinct and the condition is drawn too wide. Raising the
amount threshold on new accounts would keep most of the benefit for a fraction of the reviews.

### 4. A single-transaction rule cannot see structuring, and there is structuring

This is the finding worth reading.

Aggregating to **one row per customer per day** finds **29 days** where a user made three or
more transfers, each below the £10,000 reporting threshold, together totalling more than it —
**£0.7m** in all. **100%** of those days involve genuinely suspicious activity.

**The production rule caught 0% of them.**

![Structuring](outputs/figures/04_structuring.png)

No amount of tuning the amount threshold fixes this. Every individual transfer is
unremarkable, and the rule only ever looks at one at a time. The evidence does not exist at
transaction grain — it only appears once you aggregate. That is why
`fct_user_daily_activity` exists in the dbt project, and it is the first change I would make.

### 5. Verification method and verification outcome are different things

**83%** of users verified through Document Upload pass, against **54%** through Utility Bill.
That is an operations and conversion problem worth fixing on its own terms.

The *outcome* is a separate matter and it is a genuine risk signal: suspicious activity runs
at **2.84%** among users whose verification failed against **0.73%** among those who passed,
roughly **4 times** higher.

![KYC](outputs/figures/05_kyc.png)

Those two facts pull against each other. Making utility-bill verification easier to pass
improves conversion and also admits some of the users the failure was catching. That is a
decision about risk appetite, not a straightforward improvement, and it should be taken by
someone who owns that appetite.

---

## The data

Simulated: **10,000 users** and **~75,800 transactions** across eight corridors over six
months, from a fixed seed, so the same command always produces the same data and anyone can
check these numbers.

`src/generate.py` documents exactly what structure is planted. In short: a hidden per-user
suspicion propensity, corridors with different risk, a latent `is_suspicious` ground truth,
and a **deliberately imperfect rules-based flag** that fires on single-transaction conditions.
The gap between the flag and the ground truth is the subject of findings 2, 3 and 4.

**`is_suspicious` never leaves `data/raw/`.** It does not exist in production, so a model or
a mart built on it would score beautifully and be worthless. There is a test asserting it is
absent from the clean extract.

**The raw files are deliberately messy**, because a pipeline that has never met a bad row
proves nothing:

| Planted problem | What the pipeline does |
| --- | --- |
| 600 duplicated transactions (a replayed settlement batch) | Deduplicated on `transaction_id`, counted |
| 40 users with no home country | Kept as `Unknown`, not dropped |
| 150 corrupted exchange rates | **Quarantined, not corrected** |
| 1 signup date after that user's own transactions | Caught by a dbt test |
| 4,000 timestamps in `dd/mm/yyyy` instead of ISO | Both formats parsed |

The quarantine decision is the one I would defend hardest. When `amount × rate` does not
equal `converted_amount`, we know one of the three fields is wrong but not which. Correcting
it means guessing. Excluding the rows from value while still counting them keeps the problem
visible instead of burying it in a total.

## How it is put together

```
run.py                        one command: generate, validate, analyse, seed dbt
src/generate.py               simulation, planted structure documented
src/validate.py               data quality checks, warnings vs failures
src/analyse.py                cleaning, the five questions, charts
tests/test_pipeline.py        five tests
dbt/lemfi_analytics/
  models/staging/             stg_users, stg_transactions
  models/marts/               fct_user_daily_activity, fct_corridor_monthly, fct_kyc_funnel
  models/schema.yml           column tests: unique, not_null, accepted_values, relationships
  tests/                      three singular tests
outputs/findings.md           regenerated on every run
outputs/figures/              the charts above
```

The validator separates **warnings** from **failures**. A warning is a defect the pipeline
handles, and it is reported and counted. A failure means the analysis would be wrong and
nobody would notice — an empty table, an orphan transaction, a duplicate key surviving
cleaning — and it raises. A check that only ever prints is a check nobody reads.

### The dbt tests worth looking at

The generic tests are the usual ones. The three singular tests are where the thinking is:

- **`assert_fx_reconciles`** — every row *not* quarantined must satisfy
  `amount × rate = converted_amount`. This fails if the quarantine logic itself drifts, which
  is the kind of silent break that corrupts a volume figure for months.
- **`assert_no_transfers_before_signup`** — a transaction predating its user means a broken
  join or a bad date. Either way tenure and cohort analysis quietly stop being true.
- **`assert_daily_totals_match_transactions`** — the daily aggregate must reconcile to the
  transactions it came from. An aggregate that drops or double-counts rows is what makes a
  dashboard confidently wrong.

The reporting threshold lives in `dbt_project.yml` as a var, so the rule and the analysis
cannot drift apart. Typing a threshold into two places is how they always do.

## Running the dbt project

The CSVs are written by `python run.py`, so run that first. Then:

```bash
pip install dbt-duckdb
cd dbt/lemfi_analytics
dbt run && dbt test
```

`profiles.yml` is committed inside the project and points at DuckDB, which is a file rather
than a server, and the data is declared as an **external source** read straight from CSV. That means the dbt layer runs from a clean checkout with no database to set up
and nothing to edit in `~/.dbt/`. Swapping to PostgreSQL is a change to that one file.

**Honest note:** I could not install dbt in the environment I rebuilt this in, so the models
and tests are written but I have not executed them end to end. What I did verify is that the
`fct_user_daily_activity` logic reproduces the Python analysis exactly — the same 29
structuring days, and a reconciliation difference of 0.0 — by running the equivalent query in
pandas. If `dbt run` throws, it should be a configuration or dialect issue rather than a logic
one, and I would rather say that than imply a clean run I have not seen.

## What this is not

- **Not real data**, and not a claim about LemFi's actual transaction book.
- **Not a model.** These questions are answered with aggregation, a confusion matrix and a
  threshold curve. A classifier would have been decoration, and the honest headline is that
  the biggest available improvement is a change of grain, not a change of algorithm.
- **Not a real AML programme.** Genuine suspicious activity reporting involves typologies,
  sanctions and PEP screening, and human investigation. This models one narrow slice.
- **The generator knows the answer.** That is the only way to show a rule missing something,
  since with real data nobody knows the ground truth. It is also why every finding is stated
  against a documented plant rather than discovered from nowhere.

## Built with

Python, pandas, NumPy, matplotlib, pytest, dbt.

**Olaoluwa Olukoya** · [github.com/Carsell](https://github.com/Carsell)
