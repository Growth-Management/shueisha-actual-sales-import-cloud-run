from __future__ import annotations

from typing import Any

from file_normalization import PROVIDER_RULES


TARGET_TABLES = {
    "apple": {
        "staging": "ice-sh.ice_sh_source_staging.sh_actual_apple_data_stg",
        "production": "ice-sh.ice_sh_source.sh_actual_apple_data",
    },
    "googleplay": {
        "staging": "ice-sh.ice_sh_source_staging.sh_actual_googleplay_data_stg",
        "production": "ice-sh.ice_sh_source.sh_actual_googleplay_data",
    },
}

BIGQUERY_TYPE_BY_NORMALIZATION_TYPE = {
    "date": "DATE",
    "integer": "INT64",
    "decimal": "NUMERIC",
}


def schema_for_provider(provider: str) -> list[dict[str, str]]:
    rule = PROVIDER_RULES.get(provider)
    if rule is None:
        raise ValueError("provider must be apple or googleplay")

    types: dict[str, Any] = rule.get("types", {})
    return [
        {
            "name": column,
            "type": BIGQUERY_TYPE_BY_NORMALIZATION_TYPE.get(types.get(column), "STRING"),
            "mode": "NULLABLE",
        }
        for column in rule["columns"]
    ]


def target_table_for_provider(provider: str, table_role: str) -> str:
    provider_tables = TARGET_TABLES.get(provider)
    if provider_tables is None:
        raise ValueError("provider must be apple or googleplay")
    table = provider_tables.get(table_role)
    if table is None:
        raise ValueError("table_role must be staging or production")
    return table


def create_table_ddl_for_provider(provider: str, table_role: str, *, if_not_exists: bool = True) -> str:
    table = target_table_for_provider(provider, table_role)
    clause = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE TABLE"
    fields = ",\n".join(f"  `{field['name']}` {field['type']}" for field in schema_for_provider(provider))
    return f"{clause} `{table}` (\n{fields}\n);"


def schema_diff_for_provider(
    provider: str,
    actual_schema: list[dict[str, Any]] | None,
    *,
    table_role: str | None = None,
) -> dict[str, Any]:
    expected_schema = schema_for_provider(provider)
    table = target_table_for_provider(provider, table_role) if table_role else None

    if actual_schema is None:
        return {
            "provider": provider,
            "table_role": table_role,
            "table": table,
            "status": "missing_table",
            "expected_count": len(expected_schema),
            "actual_count": 0,
            "missing_fields": expected_schema,
            "extra_fields": [],
            "type_mismatches": [],
            "mode_mismatches": [],
            "order_mismatches": [],
        }

    actual = [_normalized_field(field) for field in actual_schema]
    expected_by_name = {field["name"]: field for field in expected_schema}
    actual_by_name = {field["name"]: field for field in actual}
    expected_names = [field["name"] for field in expected_schema]
    actual_names = [field["name"] for field in actual]

    missing_fields = [field for field in expected_schema if field["name"] not in actual_by_name]
    extra_fields = [field for field in actual if field["name"] not in expected_by_name]
    type_mismatches = [
        {
            "name": name,
            "expected": expected_by_name[name]["type"],
            "actual": actual_by_name[name]["type"],
        }
        for name in expected_names
        if name in actual_by_name and expected_by_name[name]["type"] != actual_by_name[name]["type"]
    ]
    mode_mismatches = [
        {
            "name": name,
            "expected": expected_by_name[name].get("mode", "NULLABLE"),
            "actual": actual_by_name[name].get("mode", "NULLABLE"),
        }
        for name in expected_names
        if name in actual_by_name
        and expected_by_name[name].get("mode", "NULLABLE") != actual_by_name[name].get("mode", "NULLABLE")
    ]
    order_mismatches = [
        {
            "name": name,
            "expected_index": expected_names.index(name),
            "actual_index": actual_names.index(name),
        }
        for name in expected_names
        if name in actual_by_name and expected_names.index(name) != actual_names.index(name)
    ]

    status = (
        "match"
        if not missing_fields and not extra_fields and not type_mismatches and not mode_mismatches and not order_mismatches
        else "mismatch"
    )
    return {
        "provider": provider,
        "table_role": table_role,
        "table": table,
        "status": status,
        "expected_count": len(expected_schema),
        "actual_count": len(actual),
        "missing_fields": missing_fields,
        "extra_fields": extra_fields,
        "type_mismatches": type_mismatches,
        "mode_mismatches": mode_mismatches,
        "order_mismatches": order_mismatches,
    }


def _normalized_field(field: dict[str, Any]) -> dict[str, str]:
    return {
        "name": str(field["name"]),
        "type": str(field.get("type", "STRING")).upper(),
        "mode": str(field.get("mode", "NULLABLE")).upper(),
    }
