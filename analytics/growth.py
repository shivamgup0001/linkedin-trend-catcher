ENGAGEMENT_WEIGHTS = {
    "likes": 1,
    "comments": 3,
    "reposts": 5,
}

MIN_RATE_WINDOW_HOURS = 6
MIN_BREAKOUT_BASELINE = 20


def growth_between(previous, current):
    hours = (current["observed_at"] - previous["observed_at"]).total_seconds() / 3600
    if hours <= 0:
        return None

    changes = {}
    for name in ENGAGEMENT_WEIGHTS:
        before, after = previous.get(name), current.get(name)
        changes[name] = max(0, after - before) if before is not None and after is not None else None

    if all(value is None for value in changes.values()):
        return None

    score_components = {
        name: (changes[name] or 0) * weight
        for name, weight in ENGAGEMENT_WEIGHTS.items()
    }
    score = sum(score_components.values())
    return {
        "hours": round(hours, 2),
        "previous_observed_at": previous["observed_at"],
        "current_observed_at": current["observed_at"],
        "previous_metrics": {name: previous.get(name) for name in ENGAGEMENT_WEIGHTS},
        "current_metrics": {name: current.get(name) for name in ENGAGEMENT_WEIGHTS},
        "changes": changes,
        "score_components": score_components,
        "weighted_growth": score,
        "score_per_hour": round(score / hours, 2),
    }


def trend_scores(growth, snapshot_count):
    """Return stable absolute and relative growth scores with evidence metadata."""
    hours = growth["hours"]
    effective_hours = max(hours, MIN_RATE_WINDOW_HOURS)

    if snapshot_count >= 4 and hours >= 24:
        confidence, confidence_factor = "high", 1.0
    elif snapshot_count >= 3 and hours >= MIN_RATE_WINDOW_HOURS:
        confidence, confidence_factor = "medium", 0.75
    else:
        confidence, confidence_factor = "low", 0.5

    weighted_baseline = sum(
        (growth["previous_metrics"].get(name) or 0) * weight
        for name, weight in ENGAGEMENT_WEIGHTS.items()
    )
    stabilized_growth = growth["weighted_growth"] / effective_hours
    six_hour_growth = stabilized_growth * MIN_RATE_WINDOW_HOURS

    return {
        "momentum_score": round(stabilized_growth * confidence_factor, 2),
        "breakout_score": round(
            six_hour_growth
            / max(weighted_baseline, MIN_BREAKOUT_BASELINE)
            * 100
            * confidence_factor,
            2,
        ),
        "confidence": confidence,
        "confidence_factor": confidence_factor,
        "snapshot_count": snapshot_count,
        "effective_hours": round(effective_hours, 2),
        "weighted_baseline": weighted_baseline,
    }
