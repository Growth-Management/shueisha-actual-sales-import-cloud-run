from bigquery_schema import (
    create_table_ddl_for_provider,
    schema_diff_for_provider,
    schema_for_provider,
    target_table_for_provider,
)


def test_schema_for_provider_builds_apple_schema_from_canonical_columns():
    schema = schema_for_provider("apple")

    assert schema[:8] == [
        {"name": "sales_yyyymm", "type": "STRING", "mode": "NULLABLE"},
        {"name": "start_date", "type": "DATE", "mode": "NULLABLE"},
        {"name": "end_date", "type": "DATE", "mode": "NULLABLE"},
        {"name": "upc", "type": "STRING", "mode": "NULLABLE"},
        {"name": "isrc_isbn", "type": "STRING", "mode": "NULLABLE"},
        {"name": "vendor_identifier", "type": "STRING", "mode": "NULLABLE"},
        {"name": "quantity", "type": "INT64", "mode": "NULLABLE"},
        {"name": "partner_share", "type": "NUMERIC", "mode": "NULLABLE"},
    ]
    assert len(schema) == 34


def test_schema_for_provider_builds_googleplay_schema_from_canonical_columns():
    schema = schema_for_provider("googleplay")

    assert schema[:8] == [
        {"name": "sales_yyyymm", "type": "STRING", "mode": "NULLABLE"},
        {"name": "description", "type": "STRING", "mode": "NULLABLE"},
        {"name": "transaction_date", "type": "DATE", "mode": "NULLABLE"},
        {"name": "transaction_time", "type": "STRING", "mode": "NULLABLE"},
        {"name": "tax_type", "type": "STRING", "mode": "NULLABLE"},
        {"name": "transaction_type", "type": "STRING", "mode": "NULLABLE"},
        {"name": "refund_type", "type": "STRING", "mode": "NULLABLE"},
        {"name": "product_title", "type": "STRING", "mode": "NULLABLE"},
    ]
    assert {"name": "download_count", "type": "INT64", "mode": "NULLABLE"} in schema
    assert {"name": "amount_merchant_currency", "type": "NUMERIC", "mode": "NULLABLE"} in schema
    assert len(schema) == 32


def test_target_table_for_provider_returns_canonical_bigquery_tables():
    assert target_table_for_provider("apple", "staging") == "ice-sh.ice_sh_source_staging.sh_actual_apple_data_stg"
    assert target_table_for_provider("apple", "production") == "ice-sh.ice_sh_source.sh_actual_apple_data"
    assert target_table_for_provider("googleplay", "staging") == "ice-sh.ice_sh_source_staging.sh_actual_googleplay_data_stg"
    assert target_table_for_provider("googleplay", "production") == "ice-sh.ice_sh_source.sh_actual_googleplay_data"


def test_schema_diff_for_provider_reports_missing_table():
    diff = schema_diff_for_provider("apple", None, table_role="staging")

    assert diff["status"] == "missing_table"
    assert diff["table"] == "ice-sh.ice_sh_source_staging.sh_actual_apple_data_stg"
    assert diff["expected_count"] == 34
    assert diff["actual_count"] == 0
    assert diff["missing_fields"][:3] == [
        {"name": "sales_yyyymm", "type": "STRING", "mode": "NULLABLE"},
        {"name": "start_date", "type": "DATE", "mode": "NULLABLE"},
        {"name": "end_date", "type": "DATE", "mode": "NULLABLE"},
    ]


def test_schema_diff_for_provider_reports_legacy_production_mismatches():
    actual_schema = [
        {"name": "start_date", "type": "STRING", "mode": "NULLABLE"},
        {"name": "end_date", "type": "STRING", "mode": "NULLABLE"},
        {"name": "developer", "type": "STRING", "mode": "NULLABLE"},
        {"name": "sales_yyyymm", "type": "STRING", "mode": "NULLABLE"},
    ]

    diff = schema_diff_for_provider("apple", actual_schema, table_role="production")

    assert diff["status"] == "mismatch"
    assert diff["table"] == "ice-sh.ice_sh_source.sh_actual_apple_data"
    assert {"name": "artist_show_developer_author", "type": "STRING", "mode": "NULLABLE"} in diff["missing_fields"]
    assert {"name": "developer", "type": "STRING", "mode": "NULLABLE"} in diff["extra_fields"]
    assert {"name": "start_date", "expected": "DATE", "actual": "STRING"} in diff["type_mismatches"]
    assert {"name": "sales_yyyymm", "expected_index": 0, "actual_index": 3} in diff["order_mismatches"]


def test_create_table_ddl_for_provider_uses_canonical_schema_order():
    ddl = create_table_ddl_for_provider("googleplay", "staging")

    assert ddl.startswith("CREATE TABLE IF NOT EXISTS `ice-sh.ice_sh_source_staging.sh_actual_googleplay_data_stg`")
    assert "  `sales_yyyymm` STRING,\n  `description` STRING,\n  `transaction_date` DATE" in ddl
    assert "  `download_count` INT64" in ddl
    assert "  `amount_merchant_currency` NUMERIC" in ddl
    assert ddl.endswith("\n);")
