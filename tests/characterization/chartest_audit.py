#!/usr/bin/env python3
"""
Characterization harness — TruAge AM Assignment Audit.

The audit computes live from HubSpot, so determinism comes from a RECORD/REPLAY cassette
captured at the HubSpot client boundary (`HubSpotClient._request`). Record once (needs a token +
network); thereafter snapshot/compare run OFFLINE and deterministic.

Signal captured: the structured AuditReport (counts, hygiene score, accounts_by_category,
owner_roster, inactive_owner_records) — i.e. exactly what the report shows — normalized
(drop generated_at). Rules/questions/score-history DB calls are stubbed so the snapshot is
pure and DB-independent.

USAGE
  # 1) Record a cassette from the live upstream (run once, needs creds):
  export HUBSPOT_PRIVATE_APP_TOKEN=pat-...
  python tests/characterization/chartest_audit.py record --out tests/characterization/cassette.json

  # 2) Baseline BEFORE any change (offline, from the cassette):
  python tests/characterization/chartest_audit.py snapshot \
      --cassette tests/characterization/cassette.json --out tests/characterization/baseline

  # 3) After the refactor, snapshot again, then gate:
  python tests/characterization/chartest_audit.py snapshot \
      --cassette tests/characterization/cassette.json --out tests/characterization/candidate
  python tests/characterization/chartest_audit.py compare \
      tests/characterization/baseline tests/characterization/candidate

Run from the repo root (so `pulse` imports).
"""
from __future__ import annotations
import argparse, dataclasses, json, os, sys
from collections import defaultdict, deque
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _key(method: str, path: str, kw: dict) -> str:
    body = json.dumps(kw.get("json"), sort_keys=True, default=str)
    params = json.dumps(kw.get("params"), sort_keys=True, default=str)
    return f"{method} {path} {body} {params}"


def _stub_storage():
    """Neutralize DB side-effects so the snapshot is pure/deterministic."""
    from pulse import storage
    storage.list_rules = lambda: []
    storage.list_open_questions = lambda: []
    storage.record_score = lambda *a, **k: None
    storage.record_error = lambda *a, **k: None


def _serialize(report) -> str:
    data = dataclasses.asdict(report)
    data.pop("generated_at", None)          # volatile
    data.pop("rules_of_org", None)          # stubbed to []; not part of the KPI signal
    data.pop("report_writer_questions", None)
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False, default=str)


def cmd_record(args) -> int:
    if not os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN"):
        print("ERROR: set HUBSPOT_PRIVATE_APP_TOKEN to record.", file=sys.stderr); return 2
    from pulse import hubspot_client as HC, audit
    orig = HC.HubSpotClient._request
    tape: list[dict] = []

    def rec(self, method, path, **kw):
        resp = orig(self, method, path, **kw)
        tape.append({"key": _key(method, path, kw), "resp": resp})
        return resp

    HC.HubSpotClient._request = rec
    _stub_storage()
    try:
        audit.build_audit.cache_clear()
        audit.build_audit()
    finally:
        HC.HubSpotClient._request = orig
    Path(args.out).write_text(json.dumps(tape, ensure_ascii=False), encoding="utf-8")
    print(f"recorded {len(tape)} upstream calls → {args.out}")
    return 0


def cmd_snapshot(args) -> int:
    os.environ.setdefault("HUBSPOT_PRIVATE_APP_TOKEN", "replay")  # let get_client() construct
    from pulse import hubspot_client as HC, audit
    cassette = json.loads(Path(args.cassette).read_text())
    book: dict[str, deque] = defaultdict(deque)
    for e in cassette:
        book[e["key"]].append(e["resp"])

    def rep(self, method, path, **kw):
        k = _key(method, path, kw)
        if not book[k]:
            raise RuntimeError(f"cassette miss for [{k}] — re-record (upstream shape changed).")
        return book[k].popleft()

    HC.HubSpotClient._request = rep
    _stub_storage()
    audit.build_audit.cache_clear()
    report = audit.build_audit()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(_serialize(report), encoding="utf-8")
    print(f"snapshot → {out}")
    return 0


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""

def cmd_compare(args) -> int:
    a, b = Path(args.baseline), Path(args.candidate)
    if _read(a / "metrics.json") == _read(b / "metrics.json"):
        print("✓ identical — no behavior drift (audit metrics match).")
        return 0
    print("✗ DRIFT in metrics.json")
    try:
        ma, mb = json.loads(_read(a / "metrics.json")), json.loads(_read(b / "metrics.json"))
        def flat(d, pfx=""):
            out = {}
            if isinstance(d, dict):
                for k, v in d.items(): out.update(flat(v, f"{pfx}{k}."))
            elif isinstance(d, list):
                out[pfx[:-1]] = f"<list len={len(d)}>"
            else:
                out[pfx[:-1]] = d
            return out
        fa, fb = flat(ma), flat(mb)
        for k in sorted(set(fa) | set(fb)):
            if fa.get(k) != fb.get(k):
                print(f"    {k}:  {fa.get(k)!r}  →  {fb.get(k)!r}")
    except Exception:
        print("    (metrics.json changed but could not be parsed for a field diff)")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Characterization harness for the AM Assignment Audit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record"); r.add_argument("--out", required=True); r.set_defaults(fn=cmd_record)
    s = sub.add_parser("snapshot"); s.add_argument("--cassette", required=True); s.add_argument("--out", required=True); s.set_defaults(fn=cmd_snapshot)
    c = sub.add_parser("compare"); c.add_argument("baseline"); c.add_argument("candidate"); c.set_defaults(fn=cmd_compare)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
