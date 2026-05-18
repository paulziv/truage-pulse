"""
Categorize each priority account into one of five buckets:

  Clean        — single owner across company and every contact
  Partial      — company owner matches at least one contact, others unassigned
  Overlap      — multiple active AMs across contacts (company owner included)
  Conflict     — company owner doesn't match ANY contact owner
  Orphaned     — no AM at all (company owner null, or only inactive owners)
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
from .data import CompanyRecord, AM_OWNER_IDS, INACTIVE_OWNER_IDS


@dataclass
class CategorizedAccount:
    company: CompanyRecord
    category: str           # "clean" | "partial" | "overlap" | "conflict" | "orphaned"
    company_owner_id: str | None
    contact_owner_counts: dict[str, int]  # owner_id -> count
    unowned_contact_count: int
    notes: list[str] = field(default_factory=list)


def categorize(company: CompanyRecord) -> CategorizedAccount:
    company_owner = company.owner_id

    contact_owner_counts: Counter[str] = Counter()
    unowned = 0
    for c in company.contacts:
        oid = c.get("hubspot_owner_id")
        if oid:
            contact_owner_counts[str(oid)] += 1
        else:
            unowned += 1

    notes: list[str] = []

    # Orphaned: no AM anywhere — company owner missing or inactive, AND no AM
    # owns any contact.
    company_owner_is_am = company_owner in AM_OWNER_IDS
    company_owner_is_inactive = company_owner in INACTIVE_OWNER_IDS
    am_contact_owners = {oid for oid in contact_owner_counts if oid in AM_OWNER_IDS}

    if (
        (not company_owner or company_owner_is_inactive)
        and not am_contact_owners
    ):
        return CategorizedAccount(
            company=company,
            category="orphaned",
            company_owner_id=company_owner,
            contact_owner_counts=dict(contact_owner_counts),
            unowned_contact_count=unowned,
            notes=["No active AM on company or any contact."],
        )

    # If the company is unowned but at least one AM owns a contact → Conflict
    if not company_owner:
        return CategorizedAccount(
            company=company,
            category="conflict",
            company_owner_id=None,
            contact_owner_counts=dict(contact_owner_counts),
            unowned_contact_count=unowned,
            notes=["Company has no owner; at least one contact does."],
        )

    # Conflict: company owner is set but no contact is owned by them
    company_owner_in_contacts = (
        company_owner is not None and contact_owner_counts.get(company_owner, 0) > 0
    )
    if not company_owner_in_contacts:
        # If only one owner appears across contacts and it's an AM, suggest reassigning company
        if len(am_contact_owners) == 1:
            target = next(iter(am_contact_owners))
            target_name = AM_OWNER_IDS.get(target, target)
            notes.append(
                f"All AM-owned contacts go to one owner ({target_name}); "
                "consider changing company owner."
            )
        return CategorizedAccount(
            company=company,
            category="conflict",
            company_owner_id=company_owner,
            contact_owner_counts=dict(contact_owner_counts),
            unowned_contact_count=unowned,
            notes=notes,
        )

    # Overlap: multiple ACTIVE AMs in the contact owner mix (company owner counted too)
    if len(am_contact_owners) > 1:
        return CategorizedAccount(
            company=company,
            category="overlap",
            company_owner_id=company_owner,
            contact_owner_counts=dict(contact_owner_counts),
            unowned_contact_count=unowned,
            notes=[f"Contacts owned by {len(am_contact_owners)} different AMs."],
        )

    # Partial: company AM is correct AND at least one contact is unassigned
    if unowned > 0:
        return CategorizedAccount(
            company=company,
            category="partial",
            company_owner_id=company_owner,
            contact_owner_counts=dict(contact_owner_counts),
            unowned_contact_count=unowned,
            notes=[f"{unowned} contact(s) have no owner."],
        )

    # Clean: company owner matches all contact owners, no unassigned
    non_am_contacts = [
        oid for oid in contact_owner_counts
        if oid not in AM_OWNER_IDS and oid != company_owner
    ]
    if non_am_contacts:
        # Non-AM owner appears (e.g., Patrick on Support contacts).
        # Still acceptable as "partial" — needs reassignment but the AM is right.
        return CategorizedAccount(
            company=company,
            category="partial",
            company_owner_id=company_owner,
            contact_owner_counts=dict(contact_owner_counts),
            unowned_contact_count=unowned,
            notes=[
                "Non-AM owner(s) on contacts (e.g., Support Manager) — "
                "reassign to company AM."
            ],
        )

    return CategorizedAccount(
        company=company,
        category="clean",
        company_owner_id=company_owner,
        contact_owner_counts=dict(contact_owner_counts),
        unowned_contact_count=0,
    )


def categorize_all(companies: list[CompanyRecord]) -> list[CategorizedAccount]:
    return [categorize(c) for c in companies]


def category_counts(accounts: list[CategorizedAccount]) -> dict[str, int]:
    counts = {"clean": 0, "partial": 0, "overlap": 0, "conflict": 0, "orphaned": 0}
    for a in accounts:
        counts[a.category] = counts.get(a.category, 0) + 1
    return counts
