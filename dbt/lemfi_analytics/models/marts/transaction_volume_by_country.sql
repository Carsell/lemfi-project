with txn_volume as (
    select
        country,
        date_trunc('month', created_at) as month,
        sum(transaction_amount) as total_volume
    from {{ ref('stg_transactions') }}
    group by 1, 2
)

select * from txn_volume

