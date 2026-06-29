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

STAGING_DATASET = "ice-sh.ice_sh_source_staging"
DEFAULT_DATASET_LOCATION = "US"

LEGACY_PRODUCTION_RENAMES = {
    "apple": {
        "developer": "artist_show_developer_author",
        "label": "label_studio_network_developer_publisher",
        "other_identifier": "isan_other_identifier",
        "fx_rate": "exchange_rate",
        "sales_net": "deposit_amount_jpy",
        "sales_gross": "sales_amount_jpy",
        "in_out_type": "domestic_overseas",
        "app_name": "app",
        "content_type": "sales_category",
        "pre_id": "id_excerpt",
        "campaign_price": "cp_price",
        "campaign_name": "cp",
    },
    "googleplay": {
        "producut_title": "product_title",
        "product_id": "package_id",
        "amount_marchat_currency": "amount_merchant_currency",
        "net_type": "fee_category",
        "app_name": "sales_category",
        "content_type": "content_category",
        "sales_count": "download_count",
        "sales_price": "sales_unit_price",
        "net": "fee",
        "sales_net": "deposit_amount",
        "campaign_price": "cp_price",
        "campaign_name": "cp",
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


def create_staging_dataset_ddl(*, location: str = DEFAULT_DATASET_LOCATION) -> str:
    return f'CREATE SCHEMA IF NOT EXISTS `{STAGING_DATASET}`\nOPTIONS(location="{location}");'


def production_alter_plan_for_provider(
    provider: str,
    actual_schema: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    table = target_table_for_provider(provider, "production")
    expected_schema = schema_for_provider(provider)
    if actual_schema is None:
        return {
            "provider": provider,
            "table": table,
            "statements": [],
            "notes": ["production table was not found; direct ALTER cannot be planned"],
        }

    actual = [_normalized_field(field) for field in actual_schema]
    renames = _applicable_renames(provider, actual)
    post_rename_fields = _post_rename_fields(actual, renames)
    post_rename_names = {field["name"] for field in post_rename_fields}
    missing_fields = [field for field in expected_schema if field["name"] not in post_rename_names]
    type_mismatches = _type_mismatches_after_renames(expected_schema, post_rename_fields)
    order_mismatches = _order_mismatches_after_renames(expected_schema, post_rename_fields)

    statements = []
    if renames:
        statements.append(_rename_columns_statement(table, renames))
    if missing_fields:
        statements.append(_add_columns_statement(table, missing_fields))

    notes = []
    if type_mismatches:
        notes.append(
            "Direct ALTER does not cover current type mismatches; use SELECT with SAFE_CAST and overwrite / swap when data type conversion is required."
        )
    if order_mismatches:
        notes.append("Direct ALTER cannot reorder existing BigQuery columns; canonical order requires table recreation or CTAS overwrite.")

    return {
        "provider": provider,
        "table": table,
        "statements": statements,
        "notes": notes,
        "renames": renames,
        "missing_fields": missing_fields,
        "type_mismatches": type_mismatches,
        "order_mismatches": order_mismatches,
    }


def schema_ddl_plan_for_provider(
    provider: str,
    *,
    actual_production_schema: list[dict[str, Any]] | None = None,
    location: str = DEFAULT_DATASET_LOCATION,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "staging": {
            "dataset_statement": create_staging_dataset_ddl(location=location),
            "table_statement": create_table_ddl_for_provider(provider, "staging"),
        },
        "production": production_alter_plan_for_provider(provider, actual_production_schema),
    }


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


def _applicable_renames(provider: str, actual_schema: list[dict[str, str]]) -> dict[str, str]:
    actual_names = {field["name"] for field in actual_schema}
    return {
        old_name: new_name
        for old_name, new_name in LEGACY_PRODUCTION_RENAMES.get(provider, {}).items()
        if old_name in actual_names and new_name not in actual_names
    }


def _post_rename_fields(actual_schema: list[dict[str, str]], renames: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            **field,
            "name": renames.get(field["name"], field["name"]),
        }
        for field in actual_schema
    ]


def _type_mismatches_after_renames(
    expected_schema: list[dict[str, str]],
    actual_schema: list[dict[str, str]],
) -> list[dict[str, str]]:
    actual_by_name = {field["name"]: field for field in actual_schema}
    return [
        {
            "name": field["name"],
            "expected": field["type"],
            "actual": actual_by_name[field["name"]]["type"],
        }
        for field in expected_schema
        if field["name"] in actual_by_name and field["type"] != actual_by_name[field["name"]]["type"]
    ]


def _order_mismatches_after_renames(
    expected_schema: list[dict[str, str]],
    actual_schema: list[dict[str, str]],
) -> list[dict[str, int | str]]:
    expected_names = [field["name"] for field in expected_schema]
    actual_names = [field["name"] for field in actual_schema]
    return [
        {
            "name": name,
            "expected_index": expected_names.index(name),
            "actual_index": actual_names.index(name),
        }
        for name in expected_names
        if name in actual_names and expected_names.index(name) != actual_names.index(name)
    ]


def _rename_columns_statement(table: str, renames: dict[str, str]) -> str:
    rename_clauses = ",\n".join(
        f"  RENAME COLUMN IF EXISTS `{old_name}` TO `{new_name}`" for old_name, new_name in renames.items()
    )
    return f"ALTER TABLE IF EXISTS `{table}`\n{rename_clauses};"


def _add_columns_statement(table: str, fields: list[dict[str, str]]) -> str:
    add_clauses = ",\n".join(f"  ADD COLUMN IF NOT EXISTS `{field['name']}` {field['type']}" for field in fields)
    return f"ALTER TABLE IF EXISTS `{table}`\n{add_clauses};"
