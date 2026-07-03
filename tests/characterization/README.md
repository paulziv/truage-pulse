# Characterization tests — AM Assignment Audit

Purpose: prove the audit's output is **unchanged** across a refactor. Determinism via a
record/replay cassette captured at the HubSpot client boundary.

Workflow
1. **Record a cassette once (needs creds + network):**
   `export HUBSPOT_PRIVATE_APP_TOKEN=pat-...`
   `python tests/characterization/chartest_audit.py record --out tests/characterization/cassette.json`
2. **Baseline (offline):**
   `python tests/characterization/chartest_audit.py snapshot --cassette tests/characterization/cassette.json --out tests/characterization/baseline`
3. Do the refactor, then **candidate + gate:**
   `python tests/characterization/chartest_audit.py snapshot --cassette tests/characterization/cassette.json --out tests/characterization/candidate`
   `python tests/characterization/chartest_audit.py compare tests/characterization/baseline tests/characterization/candidate`

DB side-effects (rules/questions/score history) are stubbed so snapshots are pure. Keep the
cassette + baseline out of git (throwaway). Run from the repo root.
