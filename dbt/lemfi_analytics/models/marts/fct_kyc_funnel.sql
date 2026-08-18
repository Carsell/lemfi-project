-- Verification outcome by the method a user came through. Method is an operations question;
-- the outcome is a risk signal. Keeping them in one table makes the distinction easy to
-- lose, so the grain is method x status and nothing is pre-aggregated away.
{{ config(materialized='table') }}

select
    kyc_method,
    kyc_status,
    count(*)                                        as users,
    count(*) * 1.0 / sum(count(*)) over (partition by kyc_method) as share_of_method
from {{ ref('stg_users') }}
group by 1, 2
