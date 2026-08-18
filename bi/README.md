# Power BI / Tableau model — remittance operations

A star-schema export of the cleaned pipeline output, built so the dashboard can be rebuilt from
scratch by anyone who clones this repo. Every figure below is generated from the data at runtime,
not typed.

## Files

| File | Grain | Rows |
|---|---|---|
| `fact_transactions.csv` | one transaction | 75,737 |
| `dim_user.csv` | one user | 10,000 |
| `dim_date.csv` | one calendar day | 181 |
| `data_quality_log.csv` | one quality measure | 6 |

`dim_date` covers 2025-01-01 to 2025-06-30 with no gaps. A dashboard without a date dimension
cannot do time intelligence correctly — month-on-month on a fact table alone silently skips days
where nothing happened.

## Model

    dim_date[date]  1 ──< fact_transactions[occurred_on]
    dim_user[user_id] 1 ──< fact_transactions[user_id]

Both single-direction, one-to-many. Mark `dim_date` as a date table.

## Measures (DAX)

```
Transactions      = COUNTROWS(fact_transactions)

Value Sent        = CALCULATE(SUM(fact_transactions[amount_gbp]),
                        fact_transactions[fx_reconciles] = TRUE())

Flag Rate         = DIVIDE(CALCULATE([Transactions], fact_transactions[is_flagged] = TRUE()),
                        [Transactions])

Active Users      = DISTINCTCOUNT(fact_transactions[user_id])

Quarantined Rows  = CALCULATE([Transactions], fact_transactions[fx_reconciles] = FALSE())

Value MoM %       = VAR prior = CALCULATE([Value Sent], DATEADD(dim_date[date], -1, MONTH))
                    RETURN DIVIDE([Value Sent] - prior, prior)
```

`Value Sent` deliberately filters on `fx_reconciles`. 150 transactions have an amount, a rate and
a converted amount that do not agree with each other. They are excluded from reported value but
still counted in `Transactions`, so the exclusion is visible rather than buried in a total. Any
value tile that omits that filter overstates the business by including figures known to be wrong.

## What each tile is for

**Daily value sent** — the trend line. Rising through the period.

**Top corridors by volume** — where the business actually is. UK→NG is the largest by a wide
margin at 22,571 transactions.

**Flag rate by corridor** — the tile that earns its place. Flagging is not spread evenly:
US→NG runs at 16.5% and US→UG at 11.7%, while every other corridor sits below 1%. Two corridors
carry nearly all the review workload, which is a staffing conclusion, not just a chart.

**Source extract → reported** — 76,337 rows arrived, 75,737 survived cleaning, 75,587 are
reported by value. Showing attrition on the dashboard itself means a reader can see what was
dropped without opening the pipeline.

### One honest caveat

Flag rate by *amount band* looks dramatic — 0% below £1,000, 75% above £5,000 — but that is
largely by construction, because the flagging rule is threshold-based on amount. It is a check
that the rule works, not a finding. The corridor concentration is the finding, because nothing in
the rule mentions a corridor.

## Rebuilding it

1. `python run.py` from the repo root to regenerate `data/clean/`.
2. `python bi/build_bi_model.py` to regenerate this folder.
3. Power BI Desktop → Get Data → Text/CSV → all four files → build relationships as above.
4. Add the measures, then build the tiles.

`dashboard_page1_operations.png` is the reference layout. The `.pbix` is committed alongside it.

## Note on the screenshot

The PNG in this folder was produced in matplotlib from the same model, as a layout reference for
building the Power BI version. It is a specification of the dashboard, not a screenshot of it.
The `.pbix` is the Power BI artefact.
