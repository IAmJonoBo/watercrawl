{% test email_domain_matches_website(model, column_name, website_column) %}
select
  {{ column_name }},
  {{ website_column }}
from {{ model }}
where {{ column_name }} is not null
  and {{ website_column }} is not null
  and lower(split_part({{ column_name }}, '@', 2)) != lower(regexp_extract({{ website_column }}, 'https?://([^/]+)', 1))
{% endtest %}
