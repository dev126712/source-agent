"""Seed expansion: turn a loose vibe (or nothing) into concrete search categories.

Looseness lives here, controlled by `exploration` (0..1):
  - low   -> stay close to the seed / proven arbitrage categories
  - high  -> wander widely across the category pool

Randomness plus the seen-memory filter downstream is what makes repeat runs feel
fresh even with the same seed.
"""

import random

# A broad pool the agent can wander into when exploring. In production this can
# be LLM-generated and/or biased by which categories have historically arbitraged
# well for this user.
CATEGORY_POOL = [
    "kitchen gadgets", "home organization", "outdoor gear", "pet supplies",
    "baby products", "beauty tools", "fitness accessories", "office supplies",
    "toys and games", "craft supplies", "car accessories", "garden tools",
    "small electronics", "phone accessories", "board games", "cookware",
    "cleaning supplies", "storage bins", "camping gear", "water bottles",
]

# Rough adjacency so a seed pulls in related categories at low exploration.
_ADJACENCY = {
    "kitchen gadgets": ["cookware", "home organization", "cleaning supplies"],
    "outdoor gear": ["camping gear", "water bottles", "fitness accessories"],
    "pet supplies": ["home organization", "cleaning supplies"],
    "beauty tools": ["small electronics", "fitness accessories"],
}


def expand_categories(
    *,
    seed: str | None,
    exploration: float,
    n: int,
    rng: random.Random | None = None,
) -> list[str]:
    """Return `n` search categories.

    exploration=0 with a seed -> seed + its close neighbours only.
    exploration=1 -> a wide random draw from the whole pool.
    No seed -> exploration effectively acts as breadth of the random draw.
    """
    rng = rng or random.Random()
    exploration = max(0.0, min(1.0, exploration))

    chosen: list[str] = []

    if seed:
        seed_norm = seed.strip().lower()
        chosen.append(seed_norm)
        neighbours = _ADJACENCY.get(seed_norm, [])
        # At low exploration, prefer neighbours; at high, ignore them.
        near_count = round((1 - exploration) * (n - 1))
        chosen.extend(neighbours[:near_count])

    # Fill the rest with a random draw from the pool, weighted by exploration.
    pool = [c for c in CATEGORY_POOL if c not in chosen]
    rng.shuffle(pool)
    remaining = max(0, n - len(chosen))
    chosen.extend(pool[:remaining])

    # De-dup while preserving order, cap at n.
    seen: set[str] = set()
    result: list[str] = []
    for c in chosen:
        if c not in seen:
            seen.add(c)
            result.append(c)
        if len(result) >= n:
            break
    return result
