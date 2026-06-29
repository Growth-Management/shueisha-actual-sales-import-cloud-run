from bigquery_schema import (
    create_staging_dataset_ddl,
    create_table_ddl_for_provider,
    production_alter_plan_for_provider,
    schema_diff_for_provider,
    schema_ddl_plan_for_provider,
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


def test_create_staging_dataset_ddl_uses_existing_project_location():
    assert create_staging_dataset_ddl() == 'CREATE SCHEMA IF NOT EXISTS `ice-sh.ice_sh_source_staging`\nOPTIONS(location="US");'


def test_production_alter_plan_for_apple_renames_legacy_columns_and_flags_type_or_order_limits():
    actual_schema = [
        {"name": "start_date", "type": "STRING", "mode": "NULLABLE"},
        {"name": "end_date", "type": "STRING", "mode": "NULLABLE"},
        {"name": "developer", "type": "STRING", "mode": "NULLABLE"},
        {"name": "label", "type": "STRING", "mode": "NULLABLE"},
        {"name": "sales_yyyymm", "type": "STRING", "mode": "NULLABLE"},
    ]

    plan = production_alter_plan_for_provider("apple", actual_schema)

    assert plan["renames"] == {
        "developer": "artist_show_developer_author",
        "label": "label_studio_network_developer_publisher",
    }
    assert plan["statements"][0] == (
        "ALTER TABLE IF EXISTS `ice-sh.ice_sh_source.sh_actual_apple_data`\n"
        "  RENAME COLUMN IF EXISTS `developer` TO `artist_show_developer_author`,\n"
        "  RENAME COLUMN IF EXISTS `label` TO `label_studio_network_developer_publisher`;"
    )
    assert any(field["name"] == "upc" for field in plan["missing_fields"])
    assert {"name": "start_date", "expected": "DATE", "actual": "STRING"} in plan["type_mismatches"]
    assert {"name": "sales_yyyymm", "expected_index": 0, "actual_index": 4} in plan["order_mismatches"]
    assert any("Direct ALTER does not cover current type mismatches" in note for note in plan["notes"])
    assert any("Direct ALTER cannot reorder" in note for note in plan["notes"])


def test_production_alter_plan_for_googleplay_adds_missing_canonical_columns():
    actual_schema = [
        {"name": "description", "type": "STRING", "mode": "NULLABLE"},
        {"name": "transaction_date", "type": "STRING", "mode": "NULLABLE"},
        {"name": "producut_title", "type": "STRING", "mode": "NULLABLE"},
        {"name": "product_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "amount_marchat_currency", "type": "STRING", "mode": "NULLABLE"},
        {"name": "campaign_name", "type": "STRING", "mode": "NULLABLE"},
    ]

    plan = production_alter_plan_for_provider("googleplay", actual_schema)

    assert plan["renames"] == {
        "producut_title": "product_title",
        "product_id": "package_id",
        "amount_marchat_currency": "amount_merchant_currency",
        "campaign_name": "cp",
    }
    assert "ADD COLUMN IF NOT EXISTS `sales_yyyymm` STRING" in plan["statements"][1]
    assert "ADD COLUMN IF NOT EXISTS `base_price` NUMERIC" in plan["statements"][1]
    assert "ADD COLUMN IF NOT EXISTS `tax` NUMERIC" in plan["statements"][1]


def test_schema_ddl_plan_for_provider_combines_staging_and_production_actions():
    plan = schema_ddl_plan_for_provider(
        "googleplay",
        actual_production_schema=[
            {"name": "description", "type": "STRING", "mode": "NULLABLE"},
            {"name": "producut_title", "type": "STRING", "mode": "NULLABLE"},
        ],
    )

    assert plan["staging"]["dataset_statement"] == (
        'CREATE SCHEMA IF NOT EXISTS `ice-sh.ice_sh_source_staging`\nOPTIONS(location="US");'
    )
    assert plan["staging"]["table_statement"].startswith(
        "CREATE TABLE IF NOT EXISTS `ice-sh.ice_sh_source_staging.sh_actual_googleplay_data_stg`"
    )
    assert plan["production"]["renames"] == {"producut_title": "product_title"}
