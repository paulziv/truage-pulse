"""
HubSpot client — now lives in truage-core (single source shared with the Activation Report).

This module is kept as `pulse.hubspot_client` so existing imports
(`from ..hubspot_client import HubSpotClient, get_client, HubSpotError`) keep working unchanged.
The concrete implementation — including the fail-loud retry policy — is in
truage_core.hubspot.client.

Token resolution order (get_client): explicit arg → HUBSPOT_TOKEN → HUBSPOT_PRIVATE_APP_TOKEN,
so pulse keeps working with its existing HUBSPOT_PRIVATE_APP_TOKEN until the canonical
HUBSPOT_TOKEN is set in Railway.
"""
from truage_core.hubspot.client import (  # noqa: F401
    HubSpotClient,
    HubSpotError,
    get_client,
)
