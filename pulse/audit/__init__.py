"""
AM Assignment Audit — top-level orchestration.

Call `build_audit()` to produce everything a template needs to render the report.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime

from .. import storage
from ..cache import cached
from ..hubspot_client import get_client
from . import data, analysis, score


@dataclass
class AuditReport:
    generated_at: str
    hygiene_score: score.HygieneScore
    score_explanation: str
    accounts_by_category: dict           # category -> list[CategorizedAccount-ish dict]
    owner_roster: dict                   # owner_id -> {name, role, active}
    inactive_owner_records: dict         # owner_id -> {companies: [...], contacts: [...], deals: [...]}
    rules_of_org: list                   # list of {id, rule, created_at}
    report_writer_questions: list        # list of {id, question, created_at}
    counts: dict                         # category -> count


# 5-minute per-replica perf cache: memoizes an expensive HubSpot pull so repeat
# views don't re-hit the API. Ephemeral and per-process — NOT a durable cache.
# The durable source of truth for rendered reports is the portal's Postgres
# report_cache (see pez-portal/app/daily_cache.py).
@cached(ttl=300)
def build_audit() -> AuditReport:
    client = get_client()

    # 1. Pull priority companies and hydrate contacts
    companies = data.fetch_priority_companies(client)
    data.hydrate_contacts(companies, client)

    # 2. Categorize
    categorized = analysis.categorize_all(companies)
    counts = analysis.category_counts(categorized)

    # 3. Score
    hygiene = score.compute(counts)
    explanation = score.explain(hygiene)

    # 4. Group accounts by category
    by_cat: dict[str, list] = {
        "clean": [], "partial": [], "overlap": [], "conflict": [], "orphaned": []
    }
    for acct in categorized:
        by_cat[acct.category].append({
            "id": acct.company.id,
            "name": acct.company.name,
            "domain": acct.company.domain,
            "company_owner_id": acct.company_owner_id,
            "num_contacts": acct.company.num_contacts,
            "num_deals": acct.company.num_deals,
            "contact_owner_counts": acct.contact_owner_counts,
            "unowned_contact_count": acct.unowned_contact_count,
            "notes": acct.notes,
        })

    # 5. Owner roster (for the legend / pill labels)
    roster = data.fetch_owner_roster(client)

    # 6. Inactive owner sweep — Grant, Bryan
    inactive_records = {}
    for oid, name in data.INACTIVE_OWNER_IDS.items():
        inactive_records[oid] = {
            "name": name,
            **data.fetch_inactive_owner_records(oid, client),
        }

    # 7. Rules of org + open questions (from settings DB)
    try:
        rules = storage.list_rules()
        questions = storage.list_open_questions()
    except Exception:
        rules, questions = [], []

    # 8. Persist score history
    try:
        storage.record_score("am_audit", hygiene.score, details={
            "counts": counts,
            "total": hygiene.total,
        })
    except Exception:
        pass  # storage isn't strictly required for the page to render

    return AuditReport(
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        hygiene_score=hygiene,
        score_explanation=explanation,
        accounts_by_category=by_cat,
        owner_roster=roster,
        inactive_owner_records=inactive_records,
        rules_of_org=rules,
        report_writer_questions=questions,
        counts=counts,
    )
