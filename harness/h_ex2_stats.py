"""h_ex2_stats: the interval estimators Q1 quotes.

Every number in Experiment 2's tables carries an interval, and an interval
computed wrongly is worse than none: it looks like evidence. Wilson had two
copies in the tree and Newcombe had none, so this pins the single module
that replaced them.

What is pinned, and the failure each one guards:

  1. Wilson agrees with published values to three decimals. A hand-derived
     estimator that is merely plausible is not checkable.
  2. Wilson stays inside 0 to 100 at both ends. Several EX2 cells are
     exactly 0 or 100 and the normal approximation leaves the range there.
  3. An EMPTY cell is not a confident zero. Returning (0, 0) for n = 0 has
     been read as a finding before.
  4. Newcombe stays inside -100 to 100 and behaves when either arm is at a
     boundary, which is where the Q1 contrast lives.
  5. A paired mean is a t interval over POSITIONS, not a Newcombe interval.
     Q1's contrasts are computed within position and averaged, so treating
     them as a difference of pooled proportions throws the pairing away.
  6. Fewer than two positions gives no interval rather than a point
     reported as certain.
  7. spans_zero is true for a NaN interval, so an uncomputable cell is
     never read as a positive result.

Run:  python3 h_ex2_stats.py
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
for p in (ROOT, os.path.join(ROOT, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from analysis.ex2.ex2_stats import (newcombe, paired_mean_ci,  # noqa: E402
                                    spans_zero, t95, wilson)

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + str(detail)
                                                  if detail else ""))
    if not ok:
        fails.append(label)


def close(a, b, tol=0.05):
    return abs(a - b) <= tol


# 1. Checked against an INDEPENDENT computation, not against a remembered
# table. The Wilson interval is by definition the set of p for which the
# score statistic does not exceed z:
#
#     (phat - p)^2 = z^2 * p(1 - p) / n
#
# which rearranges to a quadratic in p whose two roots ARE the bounds. That
# is a different route to the same number: the module uses the closed
# centre-and-half-width form, this solves the defining equation. Two values
# recalled from a paper were tried here first and were wrong, which is
# exactly why the check is derived rather than quoted.
def wilson_by_roots(k, n, z=1.959963984540054):
    """The bounds as roots of the score equation. Independent of wilson()."""
    phat = float(k) / n
    a = 1.0 + z * z / n
    b = -(2.0 * phat + z * z / n)
    c = phat * phat
    disc = b * b - 4 * a * c
    root = math.sqrt(max(0.0, disc))
    return (100.0 * (-b - root) / (2 * a), 100.0 * (-b + root) / (2 * a))


for k, n in ((81, 263), (15, 148), (0, 10), (7, 29), (29, 29), (1, 3)):
    got, want = wilson(k, n), wilson_by_roots(k, n)
    check("wilson %d/%d solves the score equation" % (k, n),
          close(got[0], want[0], 1e-6) and close(got[1], want[1], 1e-6),
          "closed form %.4f-%.4f, roots %.4f-%.4f"
          % (got[0], got[1], want[0], want[1]))

# And the interval must actually contain the point estimate.
for k, n in ((81, 263), (7, 29), (1, 29)):
    lo, hi = wilson(k, n)
    check("wilson %d/%d brackets the observed proportion" % (k, n),
          lo <= 100.0 * k / n <= hi,
          "%.1f not in %.1f-%.1f" % (100.0 * k / n, lo, hi))

# 2. the ends
for k, n in ((0, 15), (15, 15), (0, 1), (1, 1), (29, 29), (0, 29)):
    lo, hi = wilson(k, n)
    check("wilson %d/%d stays inside 0 to 100" % (k, n),
          0.0 <= lo <= hi <= 100.0, "%.1f-%.1f" % (lo, hi))
check("a full cell does not claim certainty",
      wilson(15, 15)[0] < 100.0,
      "15 of 15 is not proof of 100 percent: %.1f" % wilson(15, 15)[0])
check("an empty numerator does not claim certainty",
      wilson(0, 15)[1] > 0.0, "%.1f" % wilson(0, 15)[1])

# 3. the empty cell
lo, hi = wilson(0, 0)
check("an empty cell is not a number, not a zero", lo != lo and hi != hi,
      "a cell with no observations printed as 0-0 reads as a finding")
check("an empty cell differs from a real zero",
      str(wilson(0, 0)) != str(wilson(0, 1)))

# 4. Newcombe
lo, hi = newcombe(15, 15, 0, 15)
check("newcombe on a total separation stays inside the range",
      -100.0 <= lo <= hi <= 100.0 and lo > 0.0,
      "%.1f-%.1f" % (lo, hi))
check("newcombe on identical arms spans zero",
      spans_zero(*newcombe(8, 15, 8, 15)),
      str(tuple(round(x, 1) for x in newcombe(8, 15, 8, 15))))
check("newcombe is antisymmetric",
      close(newcombe(12, 15, 4, 15)[0], -newcombe(4, 15, 12, 15)[1]),
      "swapping the arms must mirror the interval")
check("newcombe widens as n falls",
      (newcombe(4, 5, 1, 5)[1] - newcombe(4, 5, 1, 5)[0])
      > (newcombe(40, 50, 10, 50)[1] - newcombe(40, 50, 10, 50)[0]))
check("newcombe on an empty arm is not a number",
      all(x != x for x in newcombe(0, 0, 3, 10)))

# 5, 6. the paired mean is over POSITIONS
_d = [100.0] * 20 + [0.0] * 9          # 29 positions, as Q1 will have
mean, lo, hi, n = paired_mean_ci(_d)
check("the paired mean counts positions, not proposals", n == 29, n)
check("the paired mean is the mean of the differences",
      close(mean, 100.0 * 20 / 29), "%.2f" % mean)
check("the paired interval brackets the mean", lo < mean < hi,
      "%.1f in %.1f-%.1f" % (mean, lo, hi))
check("a unanimous set still carries an interval of zero width",
      paired_mean_ci([100.0] * 29)[1] == 100.0)
check("one position gives a mean and NO interval",
      paired_mean_ci([50.0])[0] == 50.0
      and all(x != x for x in paired_mean_ci([50.0])[1:3]),
      "a single position reported with bounds would claim certainty")
check("no positions gives nothing at all",
      paired_mean_ci([])[3] == 0 and paired_mean_ci([])[0] != paired_mean_ci([])[0])
check("None entries are dropped, not counted as zero",
      paired_mean_ci([10.0, None, 20.0])[3] == 2
      and close(paired_mean_ci([10.0, None, 20.0])[0], 15.0),
      "a position with no contrast must not drag the mean toward zero")

# The pairing has to matter, or it is not worth doing. Same marginals, two
# different within-position patterns: consistent differences give a tight
# interval, alternating ones a wide one.
_tight = paired_mean_ci([50.0] * 29)
_wide = paired_mean_ci([100.0, 0.0] * 14 + [50.0])
check("pairing distinguishes a consistent effect from an alternating one",
      close(_tight[0], _wide[0], 2.0)
      and (_tight[2] - _tight[1]) < (_wide[2] - _wide[1]),
      "same mean, widths %.1f vs %.1f"
      % (_tight[2] - _tight[1], _wide[2] - _wide[1]))

# 7. t quantiles and the zero test
check("t95 is larger at small df", t95(2) > t95(28) > 1.96)
check("t95 falls back to the normal for large df", close(t95(200), 1.96))
check("spans_zero is true for a NaN interval",
      spans_zero(float("nan"), float("nan")),
      "an uncomputable cell must never read as a positive result")
check("spans_zero is exact at the boundary",
      spans_zero(0.0, 10.0) and spans_zero(-10.0, 0.0)
      and not spans_zero(0.1, 10.0))

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
