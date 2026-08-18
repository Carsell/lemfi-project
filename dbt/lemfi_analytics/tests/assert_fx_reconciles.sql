-- amount_sent_local * exchange_rate should equal amount_received_local.
-- Where it does not, one of the three fields is wrong and any volume figure built on it is
-- wrong too. The Python pipeline flags these rather than correcting them, because we do not
-- know which field to trust. This test fails if any unflagged row is broken, which would
-- mean the quarantine logic itself has drifted.
select
    transaction_id,
    amount_sent_local * exchange_rate as implied,
    amount_received_local
from {{ ref('stg_transactions') }}
where fx_reconciles
  and abs(amount_sent_local * exchange_rate - amount_received_local)
      > abs(amount_received_local) * 0.001 + 0.02
