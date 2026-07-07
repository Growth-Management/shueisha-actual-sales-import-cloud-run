from __future__ import annotations

from typing import Any


APPLE_PRODUCTION_COLUMNS = [
    "start_date",
    "end_date",
    "upc",
    "isrc_isbn",
    "vendor_identifier",
    "quantity",
    "partner_share",
    "extended_partner_share",
    "partner_share_currency",
    "sales_or_return",
    "apple_identifier",
    "artist_show_developer_author",
    "title",
    "label_studio_network_developer_publisher",
    "grid",
    "product_type_identifier",
    "isan_other_identifier",
    "country_of_sale",
    "pre_order_flag",
    "promo_code",
    "customer_price",
    "customer_currency",
    "currency",
    "exchange_rate",
    "deposit_amount_jpy",
    "sales_amount_jpy",
    "domestic_overseas",
    "app",
    "sales_category",
    "id_excerpt",
    "jdcn",
    "cp_price",
    "cp",
    "sales_yyyymm",
]

GOOGLEPLAY_PRODUCTION_COLUMNS = [
    "description",
    "transaction_date",
    "transaction_time",
    "tax_type",
    "transaction_type",
    "refund_type",
    "product_title",
    "package_id",
    "product_type",
    "sku_id",
    "hardware",
    "buyer_country",
    "buyer_state",
    "buyer_postal_code",
    "buyer_currency",
    "amount_buyer_currency",
    "currency_conversion_rate",
    "merchant_currency",
    "amount_merchant_currency",
    "fee_category",
    "sales_category",
    "content_category",
    "jdcn",
    "download_count",
    "sales_unit_price",
    "fee",
    "deposit_amount",
    "cp_price",
    "cp",
    "sales_yyyymm",
    "base_price",
    "tax",
]

NUMERIC_COLUMNS = {"base_price", "tax"}


def build_schema_safe_promotion_operations(
    *,
    provider: str,
    sales_yyyymm: list[str],
    staging_table: str,
    production_table: str,
) -> list[dict[str, Any]]:
    columns = _production_columns(provider)
    return [
        {
            "sales_yyyymm": month,
            "delete_sql": f"DELETE FROM `{production_table}` WHERE sales_yyyymm = '{month}'",
            "insert_sql": _insert_sql(
                columns=columns,
                provider=provider,
                staging_table=staging_table,
                production_table=production_table,
                sales_yyyymm=month,
            ),
        }
        for month in sales_yyyymm
    ]


def _production_columns(provider: str) -> list[str]:
    if provider == "apple":
        return APPLE_PRODUCTION_COLUMNS
    if provider == "googleplay":
        return GOOGLEPLAY_PRODUCTION_COLUMNS
    raise ValueError("provider must be apple or googleplay")


def _insert_sql(
    *,
    columns: list[str],
    provider: str,
    staging_table: str,
    production_table: str,
    sales_yyyymm: str,
) -> str:
    select_expressions = ", ".join(_select_expression(provider=provider, column=column) for column in columns)
    insert_columns = ", ".join(columns)
    return (
        f"INSERT INTO `{production_table}` ({insert_columns}) "
        f"SELECT {select_expressions} "
        f"FROM `{staging_table}` WHERE sales_yyyymm = '{sales_yyyymm}'"
    )


def _select_expression(*, provider: str, column: str) -> str:
    if provider == "googleplay" and column in NUMERIC_COLUMNS:
        return column
    return f"CAST({column} AS STRING)"
