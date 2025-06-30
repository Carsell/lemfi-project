with source as (
    select * from {{ source('raw', 'raw_transactions') }}
),

renamed as (
    select
        transaction_id,
        user_id,
        timestamp as created_at,
        send_country as country,
        send_currency as currency,
        amount as transaction_amount,
        converted_amount,
        transaction_type,
        device,
        is_flagged,
        exchange_rate,
        compliance_result
    from source
)

select * from renamed
