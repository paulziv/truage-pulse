"""
AM Hygiene Score: weighted blend, 0–100.

  score = (Clean × 1.0
         + Partial × 0.6
         + Overlap × 0.4
         + Conflict × 0.2
         + Orphaned × 0.0) / Total × 100

Status thresholds:
  ≥ 85   green   (mostly clean, minor cleanup)
  60–84  yellow  (real work needed)
  < 60   red     (systemic issues)
"""
from dataclasses import dataclass

WEIGHTS = {
    "clean":    1.0,
    "partial":  0.6,
    "overlap":  0.4,
    "conflict": 0.2,
    "orphaned": 0.0,
}

THRESHOLD_GREEN = 85
THRESHOLD_YELLOW = 60


@dataclass
class HygieneScore:
    score: float        # 0–100
    status: str         # "green" | "yellow" | "red"
    icon: str           # "✓" | "!" | "✕"
    label: str          # short interpretation
    counts: dict        # category -> count
    weighted_sum: float
    total: int


def compute(counts: dict[str, int]) -> HygieneScore:
    total = sum(counts.values())
    if total == 0:
        return HygieneScore(
            score=0.0, status="red", icon="✕",
            label="No accounts in scope",
            counts=counts, weighted_sum=0, total=0,
        )

    weighted = sum(counts.get(cat, 0) * WEIGHTS[cat] for cat in WEIGHTS)
    score = round(weighted / total * 100, 1)

    if score >= THRESHOLD_GREEN:
        status, icon, label = "green", "✓", "Healthy"
    elif score >= THRESHOLD_YELLOW:
        status, icon, label = "yellow", "!", "Needs attention"
    else:
        status, icon, label = "red", "✕", "Systemic issues"

    return HygieneScore(
        score=score, status=status, icon=icon, label=label,
        counts=counts, weighted_sum=weighted, total=total,
    )


def explain(score: HygieneScore) -> str:
    """One-line interpretation for the report header."""
    if score.status == "green":
        return f"{score.counts.get('clean', 0)} of {score.total} accounts clean. Minor cleanup remains."
    if score.status == "yellow":
        problem_count = score.counts.get("conflict", 0) + score.counts.get("orphaned", 0)
        return (
            f"{score.counts.get('clean', 0)} of {score.total} accounts clean; "
            f"{problem_count} need decisions, others need cleanup."
        )
    return (
        f"Only {score.counts.get('clean', 0)} of {score.total} accounts clean. "
        f"{score.counts.get('orphaned', 0)} orphaned, {score.counts.get('conflict', 0)} in conflict."
    )
