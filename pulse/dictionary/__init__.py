"""
TruAge HubSpot Data Dictionary.

Mostly static content (field catalog, pipeline IDs, metric definitions) plus
a few dynamic pieces that are best pulled live (owner roster, current pipeline
stage labels).

The static content can be edited in this file. The change log is maintained
in CHANGELOG.md at repo root.
"""
from datetime import datetime
from ..hubspot_client import get_client
from ..audit.data import fetch_owner_roster


# ── Static content ───────────────────────────────────────────────────────────
FIELD_CATALOG = [
    # (object, property, type, description, used_by, notes)
    ("Deal", "dealname", "string", "Account / deal name", "all lists", ""),
    ("Deal", "organization_name", "string", "Legal name of retailer", "5,6,7,8,11,12", "Often duplicates dealname"),
    ("Deal", "pipeline", "enum", "Pipeline ID (default = Retailer Activations)", "all", "See Pipelines tab"),
    ("Deal", "dealstage", "enum", "Current stage ID", "all", "See Pipelines tab"),
    ("Deal", "hubspot_owner_id", "number", "Deal owner", "5,6,11", ""),
    ("Deal", "createdate", "datetime", "Deal creation timestamp", "5,9,10,11", ""),
    ("Deal", "closedate", "datetime", "Date deal closed (or planned activation date)", "1,6,10,11", "Often a planning date, not historical close"),
    ("Deal", "estimated_close_date", "date", "Forecasted close date", "8", "Often placeholder values 2026-01-01 or 2026-12-31"),
    ("Deal", "hs_v2_date_entered_current_stage", "datetime", "When deal entered current stage", "2", ""),
    ("Deal", "hs_is_stalled", "bool", "HubSpot stalled flag", "3,4,12", "Native HubSpot threshold"),
    ("Deal", "hs_is_stalled_after_timestamp", "datetime", "When the deal became stalled", "3,12", ""),
    ("Deal", "blocked_reason", "enum/string", "Top-level blocker reason", "3,4", "Underused"),
    ("Deal", "engagement_status_parking_lot_1_awaiting_sw", "enum", "Status for PL1 (Awaiting SW)", "3,4", ""),
    ("Deal", "engagement_comment_parking_lot_1_awaiting_sw", "string", "Comment for PL1", "3,4", ""),
    ("Deal", "engagement_status_parking_lot_2_lab", "enum", "Status for PL2 (Lab)", "3,4", ""),
    ("Deal", "engagement_comment_parking_lot_2_lab", "string", "Comment for PL2", "3,4", ""),
    ("Deal", "engagement_status_parking_lot_3_other", "enum", "Status for PL3 (Other)", "3,4", ""),
    ("Deal", "engagement_comment_parking_lot_3_other", "string", "Comment for PL3", "3,4", ""),
    ("Deal", "pos_list", "enum/string", "POS systems at retailer", "7", "Missing = needs POS"),
    ("Deal", "fuel_list", "enum/string", "Fuel brands present", "7", "Often null"),
    ("Deal", "total_stores", "number", "Total stores at retailer", "8", "Often null on open deals"),
    ("Deal", "stores_to_activate", "number", "Stores planned for activation", "1,11", "Drives 'active doors' if populated"),
    ("Deal", "amount", "number", "Deal amount", "11", "Often null"),
    ("Deal", "get_started", "enum", "liveRollout / labSite / etc.", "10", ""),
    ("Deal", "marketing_contact_email", "string", "Marketing POC email", "7", "Missing on >99% of open deals"),
    ("Deal", "hr_training_contact_email", "string", "HR/training POC email", "7", "Two parallel fields exist; pick canonical"),
    ("Deal", "training_contact_name", "string", "Alt training POC name", "7", ""),
    ("Ticket", "subject", "string", "Ticket subject", "9", ""),
    ("Ticket", "hs_ticket_category", "enum", "Category (FEATURE_REQUEST, etc.)", "9", "Does NOT carry 'waiting on us/them' — see open Q"),
    ("Ticket", "subcategory", "string", "Subcategory", "9", ""),
    ("Ticket", "hs_ticket_priority", "enum", "URGENT/HIGH/MEDIUM/LOW", "9", ""),
    ("Ticket", "createdate", "datetime", "Ticket creation", "9", ""),
    ("Ticket", "hs_pipeline_stage", "enum", "Ticket stage (4 = closed in pipeline 0)", "9,12", ""),
]

PIPELINES = [
    ("default", "Retailer Activations", "Main pipeline for retailer onboarding deals"),
    ("868792248", "Secondary (Vendor/Leads — TBC)", "Confirm scope"),
]

STAGES = [
    ("default", "appointmentscheduled", "Appointment Scheduled", ""),
    ("default", "qualifiedtobuy", "Qualified to Buy", ""),
    ("default", "decisionmakerboughtin", "Decision Maker Bought In", ""),
    ("default", "presentationscheduled", "Presentation Scheduled", ""),
    ("default", "contractsent", "Contract Sent", ""),
    ("default", "1346410815", "(unlabeled, frequent stall)", "Confirm label"),
    ("default", "1270163972", "Awaiting SW Upgrade (Parking Lot 1)", ""),
    ("default", "1270202953", "Lab (Parking Lot 2)", ""),
    ("default", "1335845536", "Parking Lot 3 (Other)", "Confirmed"),
    ("default", "closedwon", "Closed Won", ""),
    ("default", "closedlost", "Closed Lost", ""),
]

SHARED_METRICS = [
    ("Active Door", "A store at a retailer where TruAge is live in production. Proxied as stores under closed-won deals.", "stores_to_activate / total_stores"),
    ("Active Account", "A retailer with ≥1 closed-won deal in Retailer Activations pipeline.", "dealstage=closedwon, deduped by org"),
    ("Stalled Deal", "hs_is_stalled = true OR dealstage IN parking-lot stages.", "Locked definition"),
    ("Parking Lot Account", "Open deal currently in PL1, PL2, or PL3.", "dealstage in {1270163972, 1270202953, 1335845536}"),
    ("Prior Week", "Trailing 7 days from report runtime.", "createdate / closedate"),
    ("Time in Current Stage", "NOW − hs_v2_date_entered_current_stage, in hours.", ""),
]

OPEN_QUESTIONS = [
    "Where does 'waiting on us / waiting on them' live for Service Desk tickets? (Adding fields per item 9 plan.)",
    "Where does the 'get-started form received' date live on deals? (Two pipeline-milestone fields planned.)",
    "What is the EOY 2026 doors target curve? Needed for trajectory vs. target.",
    "Per-stage time thresholds — confirm 7d/14d/14d/21d/14d/30d defaults for stages above.",
    "Which training contact field is canonical — hr_training_contact_email or training_contact_*?",
    "Which stage IDs make up 'Leads' for exclusion from pipeline-health items?",
]


def build_dictionary():
    """Assemble the dictionary view-model."""
    try:
        roster = fetch_owner_roster(get_client())
    except Exception:
        roster = {}

    return {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "field_catalog": FIELD_CATALOG,
        "pipelines": PIPELINES,
        "stages": STAGES,
        "shared_metrics": SHARED_METRICS,
        "open_questions": OPEN_QUESTIONS,
        "owner_roster": roster,
    }
