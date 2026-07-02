#!/usr/bin/env bash
# apply_truage_pulse_n1_fix.sh
#
# Fixes the N+1 API call pattern in truage-pulse's AM Assignment Audit job.
#
# BEFORE: hydrate_contacts() looped over every priority-population company
#   (58 in the current dataset) and made a serial GET to
#   /crm/v4/objects/companies/{id}/associations/contacts for each one, plus a
#   follow-up search call — up to ~2 API calls per company, observed as a
#   71-call burst in production. This ran concurrently with
#   truage-activation-report's daily HubSpot pull (same cron trigger, same
#   private-app token) and was a major contributor to the 429 burst that
#   caused the 2026-07-01 Active Stores data-loss incident.
#
# AFTER: one call to HubSpot's v4 associations batch/read endpoint for ALL
#   companies at once (chunked at HubSpot's 1,000-id cap), then one call to
#   the v3 objects batch/read endpoint for the union of contact ids (chunked
#   at HubSpot's 100-id cap). For the current ~58-71 company population this
#   collapses to ~2-4 total API calls instead of ~71-140.
#
# Usage:
#   cd /path/to/your/local/truage-pulse
#   bash apply_truage_pulse_n1_fix.sh
#
# The script verifies it's being run from the root of a truage-pulse clone,
# applies the patch with `git apply`, then byte-compiles the two changed
# files to confirm there are no syntax errors. It does NOT commit or push —
# review the diff (`git diff`) and commit when you're satisfied.

set -euo pipefail

if [[ ! -f "pulse/hubspot_client.py" || ! -f "pulse/audit/data.py" ]]; then
  echo "ERROR: run this from the root of your truage-pulse clone" \
       "(expected to find pulse/hubspot_client.py and pulse/audit/data.py here)." >&2
  exit 1
fi

if ! git diff --quiet -- pulse/hubspot_client.py pulse/audit/data.py 2>/dev/null; then
  echo "WARNING: pulse/hubspot_client.py and/or pulse/audit/data.py already have" \
       "uncommitted local changes. Applying this patch on top of them may fail" \
       "or produce unexpected results. Consider stashing or committing first." >&2
fi

PATCH_FILE="$(mktemp)"
trap 'rm -f "$PATCH_FILE"' EXIT

cat > "$PATCH_FILE" << 'PATCH_EOF'
diff --git a/pulse/audit/data.py b/pulse/audit/data.py
index 029d628..018de87 100644
--- a/pulse/audit/data.py
+++ b/pulse/audit/data.py
@@ -110,7 +110,11 @@ def fetch_inactive_owner_records(
 def fetch_contacts_for_company(
     company_id: str, client: HubSpotClient | None = None
 ) -> list[dict]:
-    """All contacts associated with a given company. Uses associations endpoint."""
+    """
+    All contacts associated with a given company. Uses the single-record
+    associations endpoint — fine for a one-off lookup, but hydrate_contacts()
+    no longer calls this in a loop; it uses the batched client methods instead.
+    """
     client = client or get_client()
     contact_ids = client.get_associations("companies", company_id, "contacts")
     if not contact_ids:
@@ -133,10 +137,41 @@ def fetch_contacts_for_company(
 def hydrate_contacts(
     companies: list[CompanyRecord], client: HubSpotClient | None = None
 ) -> None:
-    """Mutate companies in place, populating .contacts. Per-company association call."""
+    """
+    Mutate companies in place, populating .contacts.
+
+    Batched: one associations batch/read call for all companies at once
+    (chunked at 1,000), then one contacts batch/read call for the union of
+    contact ids (chunked at 100) — replacing what was previously a per-company
+    associations GET + per-company search, i.e. up to ~2 serial HubSpot calls
+    for every company in the priority population (71 calls observed in
+    production, the trigger for a 429 burst shared with the daily activation
+    report's cron run).
+    """
     client = client or get_client()
+    if not companies:
+        return
+
+    company_ids = [c.id for c in companies]
+    assoc_map = client.batch_read_associations("companies", "contacts", company_ids)
+
+    all_contact_ids = sorted({cid for ids in assoc_map.values() for cid in ids})
+    contact_records = client.batch_read_objects(
+        "contacts",
+        all_contact_ids,
+        properties=["firstname", "lastname", "email", "hubspot_owner_id"],
+    )
+    contacts_by_id = {
+        str(r["id"]): {"id": str(r["id"]), **r.get("properties", {})}
+        for r in contact_records
+    }
+
     for c in companies:
-        c.contacts = fetch_contacts_for_company(c.id, client)
+        c.contacts = [
+            contacts_by_id[cid]
+            for cid in assoc_map.get(c.id, [])
+            if cid in contacts_by_id
+        ]
 
 
 # ── Owner roster ─────────────────────────────────────────────────────────────
diff --git a/pulse/hubspot_client.py b/pulse/hubspot_client.py
index f71d95c..e61e9b1 100644
--- a/pulse/hubspot_client.py
+++ b/pulse/hubspot_client.py
@@ -141,6 +141,74 @@ class HubSpotClient:
         data = self._request("GET", path)
         return [str(r.get("toObjectId")) for r in data.get("results", [])]
 
+    def batch_read_associations(
+        self, from_type: str, to_type: str, ids: list[str | int]
+    ) -> dict[str, list[str]]:
+        """
+        Associated-object IDs for MANY source records in as few calls as possible.
+
+        Replaces N serial GETs to get_associations() (one per record) with
+        ceil(N/1000) calls to the v4 associations batch/read endpoint. HubSpot's
+        documented cap for this endpoint (effective 2025-02-10) is 1,000 ids per
+        request body: https://developers.hubspot.com/docs/api-reference/crm-associations-v4/guide
+
+        Returns {from_id: [to_id, ...]}. Every requested id gets an entry (an
+        empty list if it has no associations) so callers can index without a
+        .get(..., []) default.
+        """
+        out: dict[str, list[str]] = {str(i): [] for i in ids}
+        if not ids:
+            return out
+
+        CHUNK = 1000
+        str_ids = [str(i) for i in ids]
+        for start in range(0, len(str_ids), CHUNK):
+            inputs = [{"id": cid} for cid in str_ids[start:start + CHUNK]]
+            # A single record could in theory have >500 associations (HubSpot's
+            # per-input page size for this endpoint), so follow "after" cursors
+            # defensively. In practice no company in the AM audit gets close.
+            while inputs:
+                data = self._request(
+                    "POST",
+                    f"/crm/v4/associations/{from_type}/{to_type}/batch/read",
+                    json={"inputs": inputs},
+                )
+                next_inputs: list[dict] = []
+                for result in data.get("results", []):
+                    from_id = str(result.get("from", {}).get("id"))
+                    to_ids = [str(t.get("toObjectId")) for t in result.get("to", [])]
+                    out.setdefault(from_id, [])
+                    out[from_id].extend(to_ids)
+                    after = result.get("paging", {}).get("next", {}).get("after")
+                    if after:
+                        next_inputs.append({"id": from_id, "after": after})
+                inputs = next_inputs
+        return out
+
+    def batch_read_objects(
+        self, object_type: str, ids: list[str | int], properties: list[str]
+    ) -> list[dict]:
+        """
+        Fetch full records for MANY ids via the v3 batch/read endpoint, instead
+        of one search-with-IN-filter call per caller. HubSpot caps batch/read at
+        100 records per request body, so this chunks automatically.
+        """
+        str_ids = [str(i) for i in ids]
+        out: list[dict] = []
+        if not str_ids:
+            return out
+
+        CHUNK = 100
+        for start in range(0, len(str_ids), CHUNK):
+            chunk = str_ids[start:start + CHUNK]
+            data = self._request(
+                "POST",
+                f"/crm/v3/objects/{object_type}/batch/read",
+                json={"inputs": [{"id": cid} for cid in chunk], "properties": properties},
+            )
+            out.extend(data.get("results", []))
+        return out
+
 
 # Singleton convenience for the app
 _client: HubSpotClient | None = None
PATCH_EOF

echo "Applying patch..."
git apply --whitespace=nowarn "$PATCH_FILE"
echo "Patch applied."

echo "Byte-compiling changed files..."
python3 -m py_compile pulse/hubspot_client.py pulse/audit/data.py
echo "Compile check OK."

echo ""
echo "Done. Next steps:"
echo "  1. git diff                     # review the change"
echo "  2. python3 -m pulse.audit --dry-run   # if you have a local way to smoke-test the audit job"
echo "  3. git add -A && git commit -m 'Fix N+1 associations pattern in AM audit hydrate_contacts'"
echo "  4. git push   # Railway will redeploy"
echo ""
echo "Expected effect: hydrate_contacts() for the ~58-71 priority-population"
echo "companies drops from ~71-140 serial HubSpot API calls to ~2-4 batched calls,"
echo "removing it as a contributor to the 429 burst shared with"
echo "truage-activation-report's daily cron run."