{{ config(materialized='view', tags=['contracts', 'curated']) }}

with source as (
    select
        "Name of Organisation",
        "Province",
        "Status",
        "Website URL",
        "Contact Person",
        "Contact Number",
        "Contact Email Address",
        "Confidence"
    from read_csv_auto('{{ var("curated_source_path") }}', header=true)
),
cleaned as (
    select
        trim("Name of Organisation") as organisation_name,
        trim("Province") as province,
        trim("Status") as status,
        trim("Website URL") as website_url,
        trim("Contact Person") as contact_person,
        trim("Contact Number") as contact_number,
        trim("Contact Email Address") as contact_email_address,
        cast(
            trim(
                coalesce(cast("Confidence" as varchar), '0')
            ) as integer
        ) as confidence
    from source
)
select
    organisation_name,
    province,
    status,
    website_url,
    contact_person,
    contact_number,
    contact_email_address,
    confidence
from cleaned
