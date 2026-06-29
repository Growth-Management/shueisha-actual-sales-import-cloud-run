from bigquery_schema import schema_for_provider


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
