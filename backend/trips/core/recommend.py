"""Route-level risk summary and recommendation."""
from __future__ import annotations

from dataclasses import dataclass, field

from .checkpoints import Checkpoint
from .risk import RiskLevel


@dataclass
class RouteRisk:
    miles_by_level: dict[str, float]
    avg_risk: float
    max_level: RiskLevel
    segments: list[dict] = field(default_factory=list)

    @property
    def no_travel_miles(self) -> float:
        return self.miles_by_level[RiskLevel.NO_TRAVEL.key]

    @property
    def severe_miles(self) -> float:
        return self.miles_by_level[RiskLevel.SEVERE.key]

    @property
    def high_miles(self) -> float:
        return self.miles_by_level[RiskLevel.HIGH.key]

    def to_dict(self) -> dict:
        return {
            "miles_by_level": {k: round(v, 1) for k, v in self.miles_by_level.items()},
            "avg_risk": round(self.avg_risk, 3),
            "max_level": int(self.max_level),
            "max_level_name": self.max_level.label,
            "segments": self.segments,
        }


def summarize(checkpoints: list[Checkpoint]) -> RouteRisk:
    """Assign route miles to risk levels.

    Each stretch between two consecutive checkpoints takes the worse of its two
    ends. This is deliberately conservative: if conditions are bad at either
    end, the driver should treat the whole stretch as bad.
    """
    miles = {lvl.key: 0.0 for lvl in RiskLevel}
    weighted = 0.0
    total = 0.0
    segments = []
    max_level = RiskLevel.LOW
    for a, b in zip(checkpoints, checkpoints[1:]):
        length = max(0.0, b.mile - a.mile)
        level = max(a.risk.level, b.risk.level)
        miles[level.key] += length
        weighted += int(level) * length
        total += length
        max_level = max(max_level, level)
        segments.append({"from_mile": round(a.mile, 2), "to_mile": round(b.mile, 2), "level": int(level)})
    if len(checkpoints) == 1:
        max_level = checkpoints[0].risk.level
    avg = weighted / total if total else float(max_level)
    return RouteRisk(miles, avg, max_level, segments)


def ranking_key(risk: RouteRisk, duration_s: float) -> tuple:
    """Lexicographic order from the brief, with No Travel miles checked first.

    1. Fewest No Travel miles (a route the rules forbid can't be "best")
    2. Fewest Severe miles
    3. Fewest High miles
    4. Lowest average risk
    5. Shortest travel time

    Miles are rounded to 0.1 mi and average risk to 0.01 so floating-point
    noise can't decide a tie that should fall through to travel time.
    """
    return (
        round(risk.no_travel_miles, 1),
        round(risk.severe_miles, 1),
        round(risk.high_miles, 1),
        round(risk.avg_risk, 2),
        duration_s,
    )


_LABELS = ["No Travel miles", "Severe miles", "High miles", "average risk", "travel time"]


def _first_difference(b: tuple, o: tuple) -> int | None:
    for i in range(len(_LABELS)):
        if b[i] != o[i]:
            return i
    return None


def explain(best: dict, others: list[dict]) -> str:
    """Plain-English reason the winner was chosen.

    Compares against the runner-up, and if a faster route was passed over,
    says which risk criterion ruled it out.
    """
    if not others:
        return "Only one route was available."
    b = best["_key"]
    runner = min(others, key=lambda r: r["_key"])
    o = runner["_key"]
    i = _first_difference(b, o)
    if i is None:
        main = "Routes are equivalent on risk and time."
    elif i == 4:
        main = f"Weather risk is the same as {runner['label']}, so the faster route wins ({(o[4] - b[4]) / 60:.0f} min quicker)."
    elif i == 3:
        main = f"Tied on Severe and High miles with {runner['label']}, but lower average risk ({b[3]:.2f} vs {o[3]:.2f})."
    else:
        main = f"Fewest {_LABELS[i]}: {b[i]:.0f} mi vs {o[i]:.0f} mi on {runner['label']}."

    faster = [r for r in others if r["_key"][4] < b[4]]
    if faster:
        f = min(faster, key=lambda r: r["_key"][4])
        j = _first_difference(b, f["_key"])
        if j is not None and j < 3:
            saved = (b[4] - f["_key"][4]) / 60
            main += f" {f['label']} is {saved:.0f} min faster but has {f['_key'][j]:.0f} {_LABELS[j]}."
        elif j == 3:
            main += f" {f['label']} is faster but carries higher average risk."
    return main
