"""
HubSpot API client. Wraps the v3 CRM search and read endpoints we use across reports.

Uses a Private App access token rather than OAuth — simpler for an internal tool
and matches Anthropic's MCP behavior. Token scopes required:
  - crm.objects.companies.read
  - crm.objects.contacts.read
  - crm.objects.deals.read
  - crm.objects.owners.read
"""
import os
import time
from typing import Any
import requests

API_ROOT = "https://api.hubapi.com"


class HubSpotError(Exception):
    pass


class HubSpotClient:
    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
        if not self.token:
            raise HubSpotError(
                "Missing HUBSPOT_PRIVATE_APP_TOKEN — set it in .env or environment."
            )
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        })

    # ── Internal HTTP plumbing ──────────────────────────────────────────────
    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{API_ROOT}{path}"
        for attempt in range(3):
            try:
                resp = self.session.request(method, url, timeout=30, **kwargs)
            except requests.RequestException as exc:
                if attempt == 2:
                    raise HubSpotError(f"HubSpot request failed: {exc}") from exc
                time.sleep(1 + attempt)
                continue

            if resp.status_code == 429:
                # Rate limited — back off and retry
                time.sleep(2 ** attempt)
                continue
            if resp.status_code >= 400:
                raise HubSpotError(
                    f"HubSpot {method} {path} → {resp.status_code}: {resp.text[:500]}"
                )
            return resp.json()
        raise HubSpotError(f"HubSpot {method} {path} failed after retries")

    # ── Owners ──────────────────────────────────────────────────────────────
    def list_owners(self) -> list[dict]:
        """All HubSpot owners (users). Cached on the instance after first call."""
        if hasattr(self, "_owners_cache"):
            return self._owners_cache
        owners: list[dict] = []
        after: str | None = None
        while True:
            params = {"limit": 100}
            if after:
                params["after"] = after
            data = self._request("GET", "/crm/v3/owners", params=params)
            owners.extend(data.get("results", []))
            after = data.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
        self._owners_cache = owners
        return owners

    def owner_by_id(self, owner_id: int | str) -> dict | None:
        if not owner_id:
            return None
        oid = str(owner_id)
        for o in self.list_owners():
            if str(o.get("id")) == oid or str(o.get("ownerId")) == oid:
                return o
        return None

    # ── Generic search ──────────────────────────────────────────────────────
    def search(
        self,
        object_type: str,
        filter_groups: list[dict] | None = None,
        properties: list[str] | None = None,
        sorts: list[dict] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Paginated search across companies/contacts/deals/tickets.

        object_type: "companies" | "contacts" | "deals" | "tickets"
        filter_groups: HubSpot filterGroups payload (list of {filters:[...]})
        properties: list of property API names to return
        sorts: list of {propertyName, direction} dicts
        limit: total cap; pages of 100 are pulled until reached or exhausted
        """
        results: list[dict] = []
        after: str | None = None
        per_page = min(100, limit)

        while len(results) < limit:
            payload: dict[str, Any] = {
                "limit": per_page,
                "properties": properties or [],
            }
            if filter_groups:
                payload["filterGroups"] = filter_groups
            if sorts:
                payload["sorts"] = sorts
            if after:
                payload["after"] = after

            data = self._request(
                "POST", f"/crm/v3/objects/{object_type}/search", json=payload
            )
            page = data.get("results", [])
            results.extend(page)

            after = data.get("paging", {}).get("next", {}).get("after")
            if not after or not page:
                break
            remaining = limit - len(results)
            if remaining < per_page:
                per_page = remaining

        return results[:limit]

    def get_associations(
        self, from_type: str, from_id: str | int, to_type: str
    ) -> list[str]:
        """Return list of associated object IDs."""
        path = f"/crm/v4/objects/{from_type}/{from_id}/associations/{to_type}"
        data = self._request("GET", path)
        return [str(r.get("toObjectId")) for r in data.get("results", [])]


# Singleton convenience for the app
_client: HubSpotClient | None = None


def get_client() -> HubSpotClient:
    global _client
    if _client is None:
        _client = HubSpotClient()
    return _client
