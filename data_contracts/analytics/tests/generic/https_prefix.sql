{% test https_prefix(model, column_name) %}
select
  {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and lower({{ column_name }}) not like 'https://%'
{% endtest %}
