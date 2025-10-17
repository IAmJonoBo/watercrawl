{% test south_african_phone(model, column_name) %}
select
  {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and (
    {{ column_name }} not like '+27%'
    or length(regexp_replace({{ column_name }}, '[^0-9]', '')) != 11
  )
{% endtest %}
