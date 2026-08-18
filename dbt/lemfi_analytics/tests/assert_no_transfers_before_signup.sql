-- A transaction dated before its user signed up means the join is wrong or a date is wrong.
-- Either way, tenure and cohort analysis silently break, so this is a failure not a warning.
select
    t.transaction_id,
    t.created_on,
    u.signed_up_on
from {{ ref('stg_transactions') }} t
join {{ ref('stg_users') }} u using (user_id)
where t.created_on < u.signed_up_on - interval '1 day'
