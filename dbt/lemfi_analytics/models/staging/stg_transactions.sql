-- One row per transaction. `is_suspicious` is ground truth from the simulation and is
-- deliberately absent from the clean extract, so it cannot leak into a mart or a feature.
with source as (select * from {{ source('lemfi', 'transactions') }})

select
    transaction_id,
    user_id,
    cast(occurred_at as timestamp)         as created_at,
    cast(occurred_on as date)              as created_on,
    send_country,
    receive_country,
    send_country || '-' || receive_country as corridor,
    send_currency,
    receive_currency,
    amount                                 as amount_sent_local,
    converted_amount                       as amount_received_local,
    exchange_rate,
    amount_gbp,
    transaction_type,
    device,
    account_age_days,
    is_flagged,
    fx_reconciles
from source
