ENGAGEMENT_WEIGHTS = {
    "likes": 1,
    "comments": 3,
    "reposts": 5,
}


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
