"""Interval estimators for EX2, in one place.

WHY THIS EXISTS. Wilson was written twice, in seecheck.py and in
verify_legality.py, and Newcombe was written nowhere while the Q1 design
calls for it on every contrast. Two copies of an estimator drift; an
estimator invented inside a notebook cell cannot be tested at all.

WILSON for a single proportion. Not the normal approximation, which puts
bounds outside 0 to 100 when a cell sits at or near either end, and several
EX2 cells are exactly 0 or 100.

NEWCOMBE for a difference of proportions, built from the two Wilson
intervals rather than from a pooled standard error. Same reason: at a
boundary the normal interval on a difference is wrong in a way that matters
here, because the whole Q1 reading is "is this contrast distinguishable
from zero".

PAIRED DIFFERENCES are a separate case and are NOT Newcombe. Q1's contrasts
are computed within position and then averaged, so the unit is the position
and the quantity is a mean of 29 differences, not a difference of two
pooled proportions. That gets a t interval over positions, which is what
paired_mean_ci returns. Using Newcombe there would throw the pairing away
and report an interval wider than the evidence, which is the error the
design document warns about in the other direction.

Usage:
    from analysis.ex2.ex2_stats import wilson, newcombe, paired_mean_ci
"""

import math

Z95 = 1.959963984540054


def wilson(k, n, z=Z95):
    """(lo, hi) in PERCENT for k successes in n trials.

    An empty cell returns (nan, nan) rather than (0, 0): a cell with no
    observations is not a confident zero, and printing one as 0-0 has been
    read as a finding before.
    """
    if n <= 0:
        return (float("nan"), float("nan"))
    p = float(k) / n
    d = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / d
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / d
    return (100.0 * max(0.0, centre - half),
            100.0 * min(1.0, centre + half))


def newcombe(k1, n1, k2, n2, z=Z95):
    """(lo, hi) in PERCENT for p1 - p2, Newcombe's method 10.

    Built from the two Wilson intervals: with (l1,u1) and (l2,u2) on the
    separate proportions, the interval on the difference is

        lo = (p1 - p2) - sqrt((p1 - l1)^2 + (u2 - p2)^2)
        hi = (p1 - p2) + sqrt((u1 - p1)^2 + (p2 - l2)^2)

    which stays inside -100 to 100 and behaves when either arm is at a
    boundary.
    """
    if n1 <= 0 or n2 <= 0:
        return (float("nan"), float("nan"))
    p1, p2 = float(k1) / n1, float(k2) / n2
    l1, u1 = [x / 100.0 for x in wilson(k1, n1, z)]
    l2, u2 = [x / 100.0 for x in wilson(k2, n2, z)]
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (100.0 * max(-1.0, lo), 100.0 * min(1.0, hi))


# Two-sided 95% t quantiles, df = n - 1, for the sample sizes EX2 can
# produce. Tabulated rather than pulled from scipy: the analysis has to run
# in whichever interpreter is to hand, and one number looked up wrongly is
# worse than a dependency.
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
        7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
        13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101,
        19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064,
        25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def t95(df):
    """Two-sided 95% t quantile, falling back to the normal for large df."""
    if df <= 0:
        return float("nan")
    if df in _T95:
        return _T95[df]
    return Z95 if df > 30 else _T95[max(_T95)]


def paired_mean_ci(diffs):
    """(mean, lo, hi, n) for a list of within-position differences.

    The unit is the POSITION. Q1 computes a difference at each position and
    averages, so the interval is a t interval over positions and the
    pairing is preserved. Position varies a lot in these scenes -- which UR
    is nearer, how far the object sits from each arm -- so pairing removes
    that variance instead of letting it inflate the interval.

    Returns nan bounds for fewer than two positions rather than a point
    reported as certain.
    """
    xs = [float(d) for d in diffs if d is not None]
    n = len(xs)
    if n == 0:
        return (float("nan"), float("nan"), float("nan"), 0)
    mean = sum(xs) / n
    if n < 2:
        return (mean, float("nan"), float("nan"), n)
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    half = t95(n - 1) * math.sqrt(var / n)
    return (mean, mean - half, mean + half, n)


def spans_zero(lo, hi):
    """True when an interval includes zero, or is not a number at all."""
    if lo != lo or hi != hi:          # nan
        return True
    return lo <= 0.0 <= hi
