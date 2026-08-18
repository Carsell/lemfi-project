-- The model the whole project exists to make.
--
-- A single-transaction rule cannot detect structuring, because each individual transfer is
-- unremarkable. Aggregating to one row per customer per day is what makes the pattern
-- visible, and it is cheap. `looks_like_structuring` is the candidate rule that comes out
-- of that: three or more transfers in a day, every one below the synthetic scenario threshold, and
-- a day total above it.
{{ config(materialized='table') }}

with daily as (
    select
        user_id,
        created_on,
        count(*)                       as transfers,
        sum(amount_gbp)                as total_gbp,
        max(amount_gbp)                as largest_gbp,
        count(distinct corridor)       as corridors_used,
        bool_or(is_flagged)            as any_flagged
    from {{ ref('stg_transactions') }}
    group by 1, 2
)

select
    *,
    transfers >= 3
      and largest_gbp < {{ var('scenario_threshold') }}
      and total_gbp  > {{ var('scenario_threshold') }} as looks_like_structuring
from daily
