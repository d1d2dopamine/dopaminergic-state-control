from __future__ import annotations

import math
from typing import Iterable


def _logcomb(n: int, k: int) -> float:
    if k < 0 or k > n:
        return float("-inf")
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def hypergeom_sf(k_minus_one: int, population: int, successes: int, draws: int) -> float:
    """P[X > k_minus_one] for Hypergeom(population, successes, draws).

    Computes the first included PMF term in log-space and walks the remaining
    tail with the exact adjacent-term recurrence. This avoids hundreds of
    expensive lgamma calls per target while retaining exact hypergeometric
    probabilities up to floating-point precision.
    """
    N, K, n = int(population), int(successes), int(draws)
    if N <= 0 or K < 0 or n < 0 or K > N or n > N:
        return 1.0
    lo = max(0, n - (N - K), int(k_minus_one) + 1)
    hi = min(K, n)
    if lo > hi:
        return 0.0
    logp = _logcomb(K, lo) + _logcomb(N - K, n - lo) - _logcomb(N, n)
    if logp < -745:
        # The entire upper tail is below double-precision range at its first
        # term; returning zero is sufficient for ranking/FDR (later clamped).
        return 0.0
    term = math.exp(logp)
    total = term
    x = lo
    while x < hi:
        denom = (x + 1) * (N - K - n + x + 1)
        if denom <= 0:
            break
        term *= ((K - x) * (n - x)) / denom
        total += term
        x += 1
        if term == 0.0:
            break
    return min(1.0, max(0.0, total))


def benjamini_hochberg(pvalues: Iterable[float]) -> list[float]:
    vals = [min(1.0, max(0.0, float(p))) for p in pvalues]
    m = len(vals)
    if not m:
        return []
    order = sorted(range(m), key=lambda i: vals[i])
    out = [1.0] * m
    running = 1.0
    for rank_from_end, i in enumerate(reversed(order), start=1):
        rank = m - rank_from_end + 1
        q = vals[i] * m / rank
        running = min(running, q)
        out[i] = min(1.0, running)
    return out


def benjamini_hochberg_total(pvalues: Iterable[float], total_tests: int) -> list[float]:
    """BH correction when unlisted tests are known to have p=1.

    This lets a sparse screen correct against the full eligible target universe
    rather than only the targets that happened to receive a dopamine edge.
    """
    vals = [min(1.0, max(0.0, float(p))) for p in pvalues]
    m = max(int(total_tests), len(vals))
    if not vals:
        return []
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [1.0] * len(vals)
    running = 1.0
    # The omitted p=1 tests occupy ranks len(vals)+1..m and therefore cannot
    # lower the running minimum for the listed p-values.
    for rank_from_end, i in enumerate(reversed(order), start=1):
        rank = len(vals) - rank_from_end + 1
        q = vals[i] * m / rank
        running = min(running, q)
        out[i] = min(1.0, running)
    return out
