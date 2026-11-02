"""Viewer-first runtime: keep speech intact and share quiet visual time across beats."""
TARGET_SECONDS = 15 * 60
FLOOR_SECONDS = 10 * 60


def allocate(plan, spoken, target=TARGET_SECONDS):
    if not plan or len(plan) != len(spoken):
        raise ValueError("picture timing requires a duration for every beat")
    # Protect the cold open. Quiet time follows evidence rather than the hook.
    eligible = list(range(1, len(plan))) or [0]
    gap = max(0.0, target - sum(spoken))
    holds = [0.0] * len(plan)
    for i in eligible:
        holds[i] = gap / len(eligible)
    return [s + h for s, h in zip(spoken, holds)], holds


def apply(plan, spoken):
    target = float(plan[0].get("picture_target_s") or 0) if plan else 0
    if not target:
        return list(spoken), [0.0] * len(spoken)
    return allocate(plan, spoken, target)


def mark(text):
    if "**Picture target seconds:**" in text:
        return text
    return text.replace("\n", "\n\n**Picture target seconds:** 900\n", 1)
