"""
Pull data for the AM Assignment Audit from HubSpot.

Two distinct populations:
  1. Priority accounts — companies with ≥2 contacts AND ≥1 deal. This is the
     operational audit scope (currently 58 accounts).
  2. Owner sweep — every record owned by a designated inactive user
     (Grant, Bryan, etc.) regardless of contact/deal count. Catches orphaned
     vendor/manufacturer records that don't show up in the priority sweep.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from ..hubspot_client import HubSpotClient, get_client

# Owner-ID maps now live in truage-core — single source of truth shared with the
# Activation Report. Values are unchanged; only their home moved (Phase 1, config adoption).
from truage_core.config import (  # noqa: E402
    AM_OWNER_IDS,
    INACTIVE_OWNER_IDS,
    OTHER_OWNER_IDS,
)


@dataclass
class CompanyRecord:
    id: str
    name: str
    owner_id: str | None
    num_contacts: int
    num_deals: int
    domain: str | None = None
    contacts: list[dict] = field(default_factory=list)


def _coerce_int(v) -> int:
    try:
        return int(v) if v not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


# ── Priority population: ≥2 contacts AND ≥1 deal ─────────────────────────────
def fetch_priority_companies(client: HubSpotClient | None = None) -> list[CompanyRecord]:
    """The 58-ish companies that drive the operational audit."""
    client = client or get_client()
    raw = client.search(
        object_type="companies",
        filter_groups=[{
            "filters": [
                {"propertyName": "num_associated_contacts", "operator": "GT", "value": "1"},
                {"propertyName": "num_associated_deals",    "operator": "GTE", "value": "1"},
            ]
        }],
        properties=["name", "domain", "hubspot_owner_id",
                    "num_associated_contacts", "num_associated_deals"],
        sorts=[{"propertyName": "num_associated_contacts", "direction": "DESCENDING"}],
        limit=200,
    )
    out: list[CompanyRecord] = []
    for r in raw:
        p = r.get("properties", {})
        out.append(CompanyRecord(
            id=str(r["id"]),
            name=p.get("name") or "(unnamed)",
            owner_id=p.get("hubspot_owner_id") or None,
            num_contacts=_coerce_int(p.get("num_associated_contacts")),
            num_deals=_coerce_int(p.get("num_associated_deals")),
            domain=p.get("domain"),
        ))
    return out


# ── Inactive-owner sweep ─────────────────────────────────────────────────────
def fetch_inactive_owner_records(
    owner_id: str, client: HubSpotClient | None = None
) -> dict[str, list[dict]]:
    """All companies / contacts / deals owned by a given (typically inactive) owner."""
    client = client or get_client()
    out: dict[str, list[dict]] = {}
    for obj_type, props in [
        ("companies", ["name", "domain", "num_associated_contacts", "num_associated_deals"]),
        ("contacts",  ["firstname", "lastname", "email", "company"]),
        ("deals",     ["dealname", "dealstage", "amount", "pipeline"]),
    ]:
        raw = client.search(
            object_type=obj_type,
            filter_groups=[{
                "filters": [{"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id}]
            }],
            properties=props,
            limit=500,
        )
        out[obj_type] = [{"id": str(r["id"]), **r.get("properties", {})} for r in raw]
    return out


# ── Contacts for a given company ─────────────────────────────────────────────
def fetch_contacts_for_company(
    company_id: str, client: HubSpotClient | None = None
) -> list[dict]:
    """
    All contacts associated with a given company. Uses the single-record
    associations endpoint — fine for a one-off lookup, but hydrate_contacts()
    no longer calls this in a loop; it uses the batched client methods instead.
    """
    client = client or get_client()
    contact_ids = client.get_associations("companies", company_id, "contacts")
    if not contact_ids:
        return []
    raw = client.search(
        object_type="contacts",
        filter_groups=[{
            "filters": [{
                "propertyName": "hs_object_id",
                "operator": "IN",
                "values": contact_ids,
            }]
        }],
        properties=["firstname", "lastname", "email", "hubspot_owner_id"],
        limit=200,
    )
    return [{"id": str(r["id"]), **r.get("properties", {})} for r in raw]


def hydrate_contacts(
    companies: list[CompanyRecord], client: HubSpotClient | None = None
) -> None:
    """
    Mutate companies in place, populating .contacts.

    Batched: one associations batch/read call for all companies at once
    (chunked at 1,000), then one contacts batch/read call for the union of
    contact ids (chunked at 100) — replacing what was previously a per-company
    associations GET + per-company search, i.e. up to ~2 serial HubSpot calls
    for every company in the priority population (71 calls observed in
    production, the trigger for a 429 burst shared with the daily activation
    report's cron run).
    """
    client = client or get_client()
    if not companies:
        return

    company_ids = [c.id for c in companies]
    assoc_map = client.batch_read_associations("companies", "contacts", company_ids)

    all_contact_ids = sorted({cid for ids in assoc_map.values() for cid in ids})
    contact_records = client.batch_read_objects(
        "contacts",
        all_contact_ids,
        properties=["firstname", "lastname", "email", "hubspot_owner_id"],
    )
    contacts_by_id = {
        str(r["id"]): {"id": str(r["id"]), **r.get("properties", {})}
        for r in contact_records
    }

    for c in companies:
        c.contacts = [
            contacts_by_id[cid]
            for cid in assoc_map.get(c.id, [])
            if cid in contacts_by_id
        ]


# ── Owner roster ─────────────────────────────────────────────────────────────
# Known-name fallbacks for owners who have been deleted from HubSpot and no
# longer return from the /owners endpoint. Without these, the UI shows
# "Unknown" pills which makes the Orphaned section look broken.
_KNOWN_DELETED_OWNERS = {
    "79761095":   {"name": "Grant Bleecher", "email": None, "active": False, "role": "Inactive (separated)"},
    "1285253947": {"name": "Bryan Esser",    "email": None, "active": False, "role": "Inactive (separated)"},
}


def fetch_owner_roster(client: HubSpotClient | None = None) -> dict[str, dict]:
    """{owner_id: {name, email, active, role}} for owners that show up in our data."""
    client = client or get_client()
    roster: dict[str, dict] = {}
    for owner in client.list_owners():
        oid = str(owner.get("id"))
        roster[oid] = {
            "name": f"{owner.get('firstName', '')} {owner.get('lastName', '')}".strip(),
            "email": owner.get("email"),
            "active": not owner.get("archived", False),
            "role": _classify_owner(oid),
        }

    # Add fallbacks for owners who have been fully deleted from HubSpot and
    # therefore don't appear in the /owners endpoint anymore.
    for oid, info in _KNOWN_DELETED_OWNERS.items():
        if oid not in roster:
            roster[oid] = dict(info)

    return roster


def _classify_owner(owner_id: str) -> str:
    if owner_id in AM_OWNER_IDS:
        return "AM"
    if owner_id in INACTIVE_OWNER_IDS:
        return "Inactive (separated)"
    if owner_id in OTHER_OWNER_IDS:
        return {
            "87367233": "Support Manager",
            "89184631": "AM (NACS Foundation)",
            "78438676": "CEO",
        }.get(owner_id, "Other")
    return "Other"
