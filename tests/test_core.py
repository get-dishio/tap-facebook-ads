"""Tests standard tap features using the built-in SDK tests library."""

import os

import pytest

from tap_facebook.streams import AdAccountsStream
from tap_facebook.tap import TapFacebook

LIVE_TEST_AVAILABLE = (
    os.environ.get("TAP_FACEBOOK_ACCESS_TOKEN")
    and os.environ.get("TAP_FACEBOOK_ACCOUNT_ID")
)


def _get_live_config():
    return {
        "start_date": "2021-03-01T00:00:00Z",
        "access_token": os.environ["TAP_FACEBOOK_ACCESS_TOKEN"],
        "locations": [{"id": os.environ["TAP_FACEBOOK_ACCOUNT_ID"]}],
    }


# ---------------------------------------------------------------------------
# Integration tests (require live Facebook API credentials)
# ---------------------------------------------------------------------------

if LIVE_TEST_AVAILABLE:
    from singer_sdk.testing import SuiteConfig, get_tap_test_class

    TestTapFacebook = get_tap_test_class(
        TapFacebook,
        config=_get_live_config(),
        suite_config=SuiteConfig(
            max_records_limit=20,
            ignore_no_records_for_streams=[
                "adlabels",
                "customconversions",
            ],
        ),
    )


# ---------------------------------------------------------------------------
# Unit tests (no API credentials required)
# ---------------------------------------------------------------------------

MOCK_CONFIG = {
    "start_date": "2021-03-01T00:00:00Z",
    "access_token": "fake-token-for-unit-tests",
    "locations": [{"id": "123456789"}],
}


def test_ads_accounts_post_process():
    row = {"amount_spent": "0", "balance": "1", "min_campaign_group_spend_cap": "2"}

    ads_accounts_stream = AdAccountsStream(tap=TapFacebook(config=MOCK_CONFIG))

    post_processed_row = ads_accounts_stream.post_process(row)

    assert post_processed_row["spend_cap"] is None
    assert post_processed_row["amount_spent"] == 0
    assert post_processed_row["balance"] == 1
    assert post_processed_row["min_campaign_group_spend_cap"] == 2


def test_tap_discovers_streams():
    """Verify discovery works without API calls."""
    tap = TapFacebook(config=MOCK_CONFIG)
    streams = tap.discover_streams()
    stream_names = [s.name for s in streams]
    assert "adaccounts" in stream_names
    assert "ads" in stream_names
    assert "campaigns" in stream_names
    assert "adsets" in stream_names
    assert "creatives" in stream_names
    assert "adsinsights_default" in stream_names


def test_default_api_version():
    """Verify the default API version is v25.0."""
    tap = TapFacebook(config=MOCK_CONFIG)
    assert tap.config["api_version"] == "v25.0"


def test_start_date_optional():
    """Verify tap initializes without start_date."""
    config_no_start = {
        "access_token": "fake-token",
        "locations": [{"id": "123"}],
    }
    tap = TapFacebook(config=config_no_start)
    assert tap.config.get("start_date") is None


@pytest.mark.skipif(not LIVE_TEST_AVAILABLE, reason="No Facebook API credentials")
def test_ads_accounts_post_process_live():
    """Run post_process test with live config (same logic, validates config loading)."""
    row = {"amount_spent": "0", "balance": "1", "min_campaign_group_spend_cap": "2"}
    ads_accounts_stream = AdAccountsStream(tap=TapFacebook(config=_get_live_config()))
    post_processed_row = ads_accounts_stream.post_process(row)
    assert post_processed_row["spend_cap"] is None
