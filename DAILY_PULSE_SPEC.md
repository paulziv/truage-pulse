# Daily Sales Pulse — Build Spec

Manager-facing EOD report. Sent 6 PM ET, Mon-Fri. Opens to a single Health Score with drill-down.

The full HTML spec (with working mockup) was produced earlier as `TruAge_Daily_Pulse_Spec_v0.1.html`. This file is the short version to refer to when wiring the route.

## Sections

1. **Subject line:** `TruAge Pulse — {Day} {Mon} {DD} EOD`. Prepend ⚠️ if score dropped 5+ points or below 50.
2. **Above the fold:** big Health Score (0–100), week-over-week delta, status circle.
3. **Four summary cards:** New Deals, Closed-Won, Stalled, No-Reason Stalled.
4. **"Work these tomorrow morning":** top 5 deals ranked by urgency score (see below).
5. **Yesterday's wins:** every deal hitting closed-won in last 24h.
6. **New deals this week:** trailing 7 days, cap at 10.
7. **Crossed a threshold overnight:** conditional — hide when empty.

## Health Score composition (initial weights)

| Component | Weight |
|---|---|
| Stall rate | 35% |
| Doors velocity vs plan | 25% |
| Blocker reason completeness | 20% |
| Top-of-funnel | 10% |
| Time-in-stage health | 10% |

## Urgency score (for the top-5 action list)

```
urgency = (stores_to_activate OR total_stores OR 1)
        × stall_multiplier
        × stage_progress_multiplier
```

`stall_multiplier`:
- not stalled, not parking lot → 1.0
- stalled, no reason logged → 1.5
- stalled, reason logged → 1.2
- in parking lot, no reason → 1.3
- in parking lot, reason logged → 0.8

`stage_progress_multiplier`:
- contractsent / decisionmakerboughtin → 1.4
- qualifiedtobuy / presentationscheduled → 1.2
- appointmentscheduled / early → 1.0
- Lab / Awaiting SW → **excluded from action list**

## Implementation order

1. Wire up `pulse/daily/data.py` to pull open deals, last 7-day closed-won, last 7-day new deals.
2. Wire up `pulse/daily/score.py` mirroring the audit's score module pattern.
3. Wire up `pulse/daily/urgency.py` for the top-5 ranking.
4. Build `templates/daily.html` matching the spec's HTML mockup.
5. Add `/daily` route handler (already stubbed in `app.py`).
6. Add cron job for 6pm ET send.

## Open decisions before launch

These need answers before wiring this up (already tracked in the Dictionary's Open Questions and the audit's Report Writer Questions):

- Weekly door target for velocity-vs-plan component
- Per-stage time thresholds (currently using single 96h)
- Recipient list (just sales manager? wider?)
- Email body vs hosted URL — both are good, pick one for v1
