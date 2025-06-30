with user_signups as (
    select
        date_trunc('month', created_at) as month,
        count(user_id) as verified_users
    from {{ ref('stg_users') }}
    where kyc_status = 'Verified'
    group by 1
)

select * from user_signups

