with source as (
    select * from {{ source('raw', 'raw_users') }}
),

renamed as (
    select
        user_id,
        name as full_name,
        email,
        signup_date as created_at,
        country,
        kyc_status,
        kyc_method,
        tenure_days,
        risk_score
    from source
)

select * from renamed