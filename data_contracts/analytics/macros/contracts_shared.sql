{% macro _contracts_canonical_payload() %}
    {% set raw = env_var('CONTRACTS_CANONICAL_JSON', '') %}
    {% if not raw %}
        {% do exceptions.raise_compiler_error('CONTRACTS_CANONICAL_JSON must be set before running contracts macros.') %}
    {% endif %}
    {% do return(fromjson(raw)) %}
{% endmacro %}


{% macro contracts_province_values() %}
    {% set payload = _contracts_canonical_payload() %}
    {% do return(payload.get('provinces', [])) %}
{% endmacro %}


{% macro contracts_status_values() %}
    {% set payload = _contracts_canonical_payload() %}
    {% do return(payload.get('statuses', [])) %}
{% endmacro %}


{% macro contracts_evidence_min_confidence() %}
    {% set payload = _contracts_canonical_payload() %}
    {% set evidence = payload.get('evidence', {}) %}
    {% do return(evidence.get('minimum_confidence', 0)) %}
{% endmacro %}


{% test contracts_min_confidence(model, column_name) %}
    select *
    from {{ model }}
    where {{ column_name }} < {{ contracts_evidence_min_confidence() }}
{% endtest %}


{% test contracts_accepted_values(model, column_name, canonical_key) %}
    {% set payload = _contracts_canonical_payload() %}
    {% set allowed = payload.get(canonical_key, []) %}
    {% if not allowed %}
        {% do exceptions.raise_compiler_error('No canonical values configured for ' ~ canonical_key) %}
    {% endif %}

    select *
    from {{ model }}
    where {{ column_name }} not in (
        {%- for value in allowed -%}
            '{{ value | replace("'", "''") }}'{% if not loop.last %}, {% endif %}
        {%- endfor -%}
    )
{% endtest %}
