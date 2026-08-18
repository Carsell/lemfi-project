-- Volume and alert load by corridor and month. Rows failing FX reconciliation are excluded
-- from value, because a wrong exchange rate silently corrupts a volume figure, but they are
-- still counted so the exclusion is visible rather than hidden.
{{ config(materialized='table') }}

select
    corridor,
    send_country,
    receive_country,
    date_trunc('month', created_at)                             as month,
    count(*)                                                    as transfers,
    sum(case when fx_reconciles then amount_gbp else 0 end)     as volume_gbp,
    count(*) filter (where not fx_reconciles)                   as excluded_fx_errors,
    count(*) filter (where is_flagged)                          as alerts,
    avg(amount_gbp)                                             as avg_transfer_gbp
from {{ ref('stg_transactions') }}
group by 1, 2, 3, 4
