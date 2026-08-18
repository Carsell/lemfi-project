-- One row per user, read straight from the CSV written by `python run.py`.
with source as (select * from {{ source('lemfi', 'users') }})

select
    user_id,
    cast(signup_date as date)              as signed_up_on,
    coalesce(home_country, 'Unknown')      as home_country,
    kyc_status,
    kyc_method,
    kyc_status = 'Verified'                as is_verified
from source
