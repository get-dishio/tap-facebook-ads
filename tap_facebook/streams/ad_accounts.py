"""Stream class for AdAccounts."""

from __future__ import annotations

import typing as t

from singer_sdk.streams.core import REPLICATION_INCREMENTAL
from singer_sdk.typing import (
    ArrayType,
    BooleanType,
    IntegerType,
    NumberType,
    PropertiesList,
    Property,
    StringType,
)

from tap_facebook.client import FacebookStream


class AdAccountsStream(FacebookStream):
    """https://developers.facebook.com/docs/graph-api/reference/user/accounts/."""

    """
    columns: columns which will be added to fields parameter in api
    name: stream name
    account_id: facebook account
    path: path which will be added to api url in client.py
    schema: instream schema
    tap_stream_id = stream id
    """

    @property
    def url_base(self) -> str:
        version = self.config.get("api_version") or "v25.0"
        return f"https://graph.facebook.com/{version}/me"


    @property
    def columns(self) -> list[str]:
        columns = [
        "account_id",
        "business_name",
        "account_status",
        "age",
        "amount_spent",
        "balance",
        "business_city",
        "business_country_code",
        "business_street",
        "business_street2",
        "can_create_brand_lift_study",
        "capabilities",
        "created_time",
        "currency",
        "disable_reason",
        "end_advertiser",
        "end_advertiser_name",
        "has_migrated_permissions",
        "id",
        "is_attribution_spec_system_default",
        "is_direct_deals_enabled",
        "is_in_3ds_authorization_enabled_market",
        "is_notifications_enabled",
        "is_personal",
        "is_prepay_account",
        "is_tax_id_required",
        "min_campaign_group_spend_cap",
        "min_daily_budget",
        "name",
        "offsite_pixels_tos_accepted",
        "spend_cap",
        "tax_id_status",
        "tax_id_type",
        "timezone_id",
        "timezone_name",
        "timezone_offset_hours_utc",
        "agency_client_declaration_agency_representing_client",
        "agency_client_declaration_client_based_in_france",
        "agency_client_declaration_client_city",
        "agency_client_declaration_client_country_code",
        "agency_client_declaration_client_email_address",
        "agency_client_declaration_client_name",
        "agency_client_declaration_client_postal_code",
        "agency_client_declaration_client_province",
        "agency_client_declaration_client_street",
        "agency_client_declaration_client_street2",
        "agency_client_declaration_has_written_mandate_from_advertiser",
        "agency_client_declaration_is_client_paying_invoices",
        "business_manager_block_offline_analytics",
        "business_manager_created_by",
        "business_manager_created_time",
        "business_manager_extended_updated_time",
        "business_manager_is_hidden",
        "business_manager_link",
        "business_manager_name",
        "business_manager_payment_account_id",
        "business_manager_primary_page",
        "business_manager_profile_picture_uri",
        "business_manager_timezone_id",
        "business_manager_two_factor_type",
        "business_manager_updated_by",
        "business_manager_update_time",
        "business_manager_verification_status",
        "business_manager_vertical",
        "business_manager_vertical_id",
        "business_manager_manager_id",
        "extended_credit_invoice_group_id",
        "extended_credit_invoice_group_auto_enroll",
        "extended_credit_invoice_group_customer_po_number",
        "extended_credit_invoice_group_email",
        "extended_credit_invoice_group_emails",
        "extended_credit_invoice_group_name",
        "business_state",
        "io_number",
        "media_agency",
        "partner",
     "business_zip",
        "tax_id",
        ]

        return columns

    name = "adaccounts"
    path = "/adaccounts"
    tap_stream_id = "adaccounts"
    primary_keys = ["created_time"]  # noqa: RUF012
    replication_key = "created_time"
    replication_method = REPLICATION_INCREMENTAL

    schema = PropertiesList(
        Property("account_id", StringType),
        Property("timezone_id", IntegerType),
        Property("business_name", StringType),
        Property("account_status", IntegerType),
        Property("age", NumberType),
        Property("amount_spent", IntegerType),
        Property("balance", IntegerType),
        Property("business_city", StringType),
        Property("business_country_code", StringType),
        Property("business_street", StringType),
        Property("business_street2", StringType),
        Property("can_create_brand_lift_study", BooleanType),
        Property("capabilities", ArrayType(StringType)),
        Property("created_time", StringType),
        Property("currency", StringType),
        Property("disable_reason", IntegerType),
        Property("end_advertiser", StringType),
        Property("end_advertiser_name", StringType),
        Property("has_migrated_permissions", BooleanType),
        Property("id", StringType),
        Property("is_attribution_spec_system_default", BooleanType),
        Property("is_direct_deals_enabled", BooleanType),
        Property("is_in_3ds_authorization_enabled_market", BooleanType),
        Property("is_notifications_enabled", BooleanType),
        Property("is_personal", IntegerType),
        Property("is_prepay_account", BooleanType),
        Property("is_tax_id_required", BooleanType),
        Property("min_campaign_group_spend_cap", IntegerType),
        Property("min_daily_budget", IntegerType),
        Property("name", StringType),
        Property("offsite_pixels_tos_accepted", BooleanType),
        Property("spend_cap", IntegerType),
        Property("tax_id_status", IntegerType),
        Property("tax_id_type", StringType),
        Property("timezone_id", IntegerType),
        Property("timezone_name", StringType),
        Property("timezone_offset_hours_utc", NumberType),
        Property("agency_client_declaration_agency_representing_client", IntegerType),
        Property("agency_client_declaration_client_based_in_france", IntegerType),
        Property("agency_client_declaration_client_city", StringType),
        Property("agency_client_declaration_client_country_code", StringType),
        Property("agency_client_declaration_client_email_address", StringType),
        Property("agency_client_declaration_client_name", StringType),
        Property("agency_client_declaration_client_postal_code", StringType),
        Property("agency_client_declaration_client_province", StringType),
        Property("agency_client_declaration_client_street", StringType),
        Property("agency_client_declaration_client_street2", StringType),
        Property(
            "agency_client_declaration_has_written_mandate_from_advertiser",
            IntegerType,
        ),
        Property("agency_client_declaration_is_client_paying_invoices", IntegerType),
        Property("business_manager_block_offline_analytics", BooleanType),
        Property("business_manager_created_by", StringType),
        Property("business_manager_created_time", StringType),
        Property("business_manager_extended_updated_time", StringType),
        Property("business_manager_is_hidden", BooleanType),
        Property("business_manager_link", StringType),
        Property("business_manager_name", StringType),
        Property("business_manager_payment_account_id", IntegerType),
        Property("business_manager_primary_page", StringType),
        Property("business_manager_profile_picture_uri", StringType),
        Property("business_manager_timezone_id", IntegerType),
        Property("business_manager_two_factor_type", StringType),
        Property("business_manager_updated_by", StringType),
        Property("business_manager_update_time", StringType),
        Property("business_manager_verification_status", StringType),
        Property("business_manager_vertical", StringType),
        Property("business_manager_vertical_id", IntegerType),
        Property("business_manager_manager_id", IntegerType),
        Property("extended_credit_invoice_group_id", IntegerType),
        Property("extended_credit_invoice_group_auto_enroll", BooleanType),
        Property("extended_credit_invoice_group_customer_po_number", StringType),
        Property("extended_credit_invoice_group_email", StringType),
        Property("extended_credit_invoice_group_emails", StringType),
        Property("extended_credit_invoice_group_name", StringType),
        Property("business_state", StringType),
        Property("io_number", IntegerType),
        Property("media_agency", StringType),
        Property("partner", StringType),

        Property("business_zip", StringType),
        Property("tax_id", StringType),
    ).to_dict()

    def post_process(
        self,
        row: dict,
        context: dict | None = None,
    ) -> dict | None:
        row["amount_spent"] = int(row["amount_spent"]) if "amount_spent" in row else None
        row["balance"] = int(row["balance"]) if "balance" in row else None
        row["min_campaign_group_spend_cap"] = (
            int(row["min_campaign_group_spend_cap"])
            if "min_campaign_group_spend_cap" in row
            else None
        )
        row["spend_cap"] = int(row["spend_cap"]) if "spend_cap" in row else None

        self.logger.info(
            "Post-processed ad account row: raw_id=%s raw_account_id=%s normalized_account_id=%s",
            row.get("id"),
            row.get("account_id"),
            self._normalize_account_id(row.get("account_id"))
            or self._normalize_account_id(row.get("id")),
        )

        return row

    def get_records(self, context):
        if not self.selected and self.configured_location_ids:
            self.logger.info(
                "adaccounts stream not selected; emitting configured locations directly: %s",
                self.configured_location_ids,
            )
            for account_id in self.configured_location_ids:
                yield {"account_id": account_id, "id": account_id}
            return

        yield from super().get_records(context)

    def get_url_params(
        self,
        context: dict | None,
        next_page_token: t.Any | None,
    ) -> dict[str, t.Any]:
        """Return a dictionary of values to be used in URL parameterization.

        Args:
            context: The stream context.
            next_page_token: The next page index or value.

        Returns:
            A dictionary of URL query parameters.
        """
        params: dict = {"limit": 25}
        if next_page_token is not None:
            params["after"] = next_page_token

        params["fields"] = ",".join(self.columns)

        return params


    def get_child_context(self, record, context):
        raw_account_id = record.get("account_id")
        raw_id = record.get("id")

        normalized_account_id = (
            self._normalize_account_id(raw_account_id)
            or self._normalize_account_id(raw_id)
        )

        child_context = {
            "account_id": normalized_account_id,
            "_raw_account_id": raw_account_id,
            "_raw_id": raw_id,
        }

        self.logger.info(
            "Built child context for ad account: raw_id=%s raw_account_id=%s normalized_account_id=%s",
            raw_id,
            raw_account_id,
            normalized_account_id,
        )

        return child_context


    def _sync_children(self, child_context: dict | None) -> None:
        if not child_context:
            self.logger.warning("Skipping child sync because child_context is empty")
            return

        normalized_child_account_id = self._normalize_account_id(
            child_context.get("account_id")
        )

        configured_ids = {
            normalized
            for normalized in (
                self._normalize_account_id(value)
                for value in self.configured_location_ids
            )
            if normalized
        }

        self.logger.info(
            "Evaluating child sync: raw_id=%s raw_account_id=%s normalized_child_account_id=%s configured_ids=%s",
            child_context.get("_raw_id"),
            child_context.get("_raw_account_id"),
            normalized_child_account_id,
            sorted(configured_ids),
        )

        if configured_ids and normalized_child_account_id not in configured_ids:
            self.logger.warning(
                "Skipping child sync for ad account because normalized_child_account_id=%s not in configured_ids=%s "
                "(raw_id=%s raw_account_id=%s)",
                normalized_child_account_id,
                sorted(configured_ids),
                child_context.get("_raw_id"),
                child_context.get("_raw_account_id"),
            )
            return

        if not normalized_child_account_id:
            self.logger.warning(
                "Skipping child sync because no usable account_id was found "
                "(raw_id=%s raw_account_id=%s)",
                child_context.get("_raw_id"),
                child_context.get("_raw_account_id"),
            )
            return

        self.logger.info(
            "Running child sync for normalized_child_account_id=%s",
            normalized_child_account_id,
        )

        super()._sync_children(
            {
                **child_context,
                "account_id": normalized_child_account_id,
            },
        )

    @staticmethod
    def _normalize_account_id(value: t.Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if normalized.startswith("act_"):
            normalized = normalized[4:]
        return normalized or None

    @property
    def configured_location_ids(self) -> list[str]:
        location_ids: list[str] = []
        locations_config = self.config.get("locations")

        if locations_config:
            if isinstance(locations_config, list):
                for entry in locations_config:
                    if isinstance(entry, dict) and "id" in entry:
                        location_ids.append(str(entry["id"]))
                    elif isinstance(entry, str):
                        location_ids.append(entry)
            elif isinstance(locations_config, str):
                location_ids.extend([item.strip() for item in locations_config.split(",")])

        normalized_ids: list[str] = []
        for location_id in location_ids:
            normalized = self._normalize_account_id(location_id)
            if normalized and normalized not in normalized_ids:
                normalized_ids.append(normalized)

        return normalized_ids
