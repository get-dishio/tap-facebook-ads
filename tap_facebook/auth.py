"""OAuth2 authenticator for Facebook Marketing API with token refresh."""

from __future__ import annotations

import json
import typing as t
from datetime import datetime, timezone

import backoff
import requests
from requests.exceptions import ConnectionError as RequestsConnectionError
from singer_sdk.authenticators import APIAuthenticatorBase

if t.TYPE_CHECKING:
    from singer_sdk.streams import Stream as RESTStreamBase


class EmptyResponseError(Exception):
    """Raised when the response is empty."""


class OAuth2Authenticator(APIAuthenticatorBase):
    """Facebook OAuth2 authenticator with automatic token refresh.

    Supports two modes:
    1. Bearer token only: config has `access_token` but no OAuth credentials.
       Uses the token as-is without refresh.
    2. Full OAuth: config has `access_token`, `client_id`, `client_secret`,
       and optionally `expires_at`. Refreshes the token via fb_exchange_token
       grant and writes it back to config.json.
    """

    def __init__(
        self,
        stream: RESTStreamBase,
        config_file: str | None = None,
        auth_endpoint: str | None = None,
    ) -> None:
        super().__init__(stream=stream)
        self._auth_endpoint = auth_endpoint
        self._config_file = config_file
        self._tap = stream._tap

    @property
    def _can_refresh(self) -> bool:
        """Check if OAuth credentials are present for token refresh."""
        return bool(
            self._tap._config.get("client_id")
            and self._tap._config.get("client_secret")
        )

    def __call__(self, r):
        """Attach auth headers to the request, refreshing the token if needed."""
        if self._can_refresh and not self.is_token_valid():
            self.update_access_token()
        self.auth_headers = {
            "Authorization": f"Bearer {self._tap._config.get('access_token')}",
        }
        return super().__call__(r)

    @property
    def oauth_request_body(self) -> dict:
        """Define the OAuth request body for the Facebook API."""
        return {
            "fb_exchange_token": self._tap._config["access_token"],
            "grant_type": "fb_exchange_token",
            "client_id": self._tap._config["client_id"],
            "client_secret": self._tap._config["client_secret"],
        }

    def is_token_valid(self) -> bool:
        access_token = self._tap._config.get("access_token")
        if not access_token:
            return False
        # If no OAuth credentials, can't refresh — assume token is valid
        if not self._can_refresh:
            return True
        expires_at = self._tap.config.get("expires_at")
        if not expires_at:
            # Has OAuth creds but no expiry — token might be long-lived, assume valid
            return True
        now = round(datetime.now(tz=timezone.utc).timestamp())
        expires_at = int(expires_at)
        # Refresh 10 days before expiration in case tap doesn't run often
        return not ((expires_at - now) < 864000)

    @backoff.on_exception(
        backoff.expo,
        (EmptyResponseError, ConnectionError, RequestsConnectionError),
        max_tries=5,
        factor=3,
    )
    def update_access_token(self) -> None:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        token_response = requests.get(
            self._auth_endpoint,
            params=self.oauth_request_body,
            headers=headers,
            timeout=30,
        )

        try:
            token_response.raise_for_status()
            self.logger.info("OAuth authorization attempt was successful.")
        except Exception as ex:
            msg = f"Failed OAuth login, response was '{token_response.json()}'. {ex}"
            raise RuntimeError(msg) from ex

        token_json = token_response.json()
        self._tap._config["access_token"] = token_json["access_token"]

        if "expires_in" in token_json:
            now = round(datetime.now(tz=timezone.utc).timestamp())
            self._tap._config["expires_at"] = int(token_json["expires_in"]) + now

        if self._config_file:
            with open(self._config_file, "w") as outfile:
                json.dump(self._tap._config, outfile, indent=4)
