from src.pipeline_defaults import apply_execution_defaults


RUN_CONTEXT = {
    "environment": "prod",
    "trigger_source": "manual_cloudshell",
    "run_id": "manual__apple__202605",
    "run_started_at": "2026-07-08T00:00:00Z",
    "run_finished_at": "2026-07-08T00:01:00Z",
    "is_test": False,
    "execution_mode": "full",
}


def test_apply_execution_defaults_adds_apple_schema_safe_promotion_sql():
    result = apply_execution_defaults(
        {
            "provider": "apple",
            "sales_yyyymm": ["202605"],
            "run_context": RUN_CONTEXT,
        }
    )

    operation = result["bigquery"]["promotion_operations"][0]
    assert operation["delete_sql"] == "DELETE FROM `ice-sh.ice_sh_source.sh_actual_apple_data` WHERE sales_yyyymm = '202605'"
    assert operation["insert_sql"].startswith(
        "INSERT INTO `ice-sh.ice_sh_source.sh_actual_apple_data` "
        "(start_date, end_date, upc, isrc_isbn, vendor_identifier"
    )
    assert "SELECT CAST(start_date AS STRING), CAST(end_date AS STRING)" in operation["insert_sql"]
    assert "CAST(sales_yyyymm AS STRING)" in operation["insert_sql"]
    assert "SELECT *" not in operation["insert_sql"]


def test_apply_execution_defaults_adds_googleplay_schema_safe_promotion_sql():
    result = apply_execution_defaults(
        {
            "provider": "googleplay",
            "sales_yyyymm": ["202605"],
            "run_context": RUN_CONTEXT,
        }
    )

    operation = result["bigquery"]["promotion_operations"][0]
    assert operation["delete_sql"] == "DELETE FROM `ice-sh.ice_sh_source.sh_actual_googleplay_data` WHERE sales_yyyymm = '202605'"
    assert operation["insert_sql"].startswith(
        "INSERT INTO `ice-sh.ice_sh_source.sh_actual_googleplay_data` "
        "(description, transaction_date, transaction_time, tax_type"
    )
    assert "CAST(transaction_date AS STRING)" in operation["insert_sql"]
    assert "CAST(sales_yyyymm AS STRING), base_price, tax" in operation["insert_sql"]
    assert "SELECT *" not in operation["insert_sql"]


def test_apply_execution_defaults_keeps_explicit_promotion_operations():
    explicit_operations = [
        {
            "sales_yyyymm": "202605",
            "delete_sql": "DELETE custom",
            "insert_sql": "INSERT custom",
        }
    ]

    result = apply_execution_defaults(
        {
            "provider": "apple",
            "sales_yyyymm": ["202605"],
            "run_context": RUN_CONTEXT,
            "bigquery": {"promotion_operations": explicit_operations},
        }
    )

    assert result["bigquery"]["promotion_operations"] == explicit_operations
