-- The daily aggregate must reconcile to the transactions it came from. An aggregate that
-- quietly drops or double-counts rows is the failure mode that makes a dashboard confidently
-- wrong, and it is invisible unless something checks it.
with from_txns as (
    select sum(amount_gbp) as total from {{ ref('stg_transactions') }}
),
from_daily as (
    select sum(total_gbp) as total from {{ ref('fct_user_daily_activity') }}
)
select from_txns.total, from_daily.total
from from_txns, from_daily
where abs(from_txns.total - from_daily.total) > 1
