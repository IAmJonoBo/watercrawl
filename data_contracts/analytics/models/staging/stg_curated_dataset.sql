{{ config(materialized='view', tags=['contracts', 'curated']) }}

with source as (
    select
        *
    from read_csv_auto('{{ var("curated_source_path") }}', header=true)
)
select
    trim("Name of Organisation") as organisation_name,
    trim("Province") as province,
    trim("Status") as status,
    trim("Website URL") as website_url,
    trim("Contact Person") as contact_person,
    trim("Contact Number") as contact_number,
    trim("Contact Email Address") as contact_email_address,
    cast(coalesce(cast("Confidence" as varchar), '0') as integer) as confidence
from source
