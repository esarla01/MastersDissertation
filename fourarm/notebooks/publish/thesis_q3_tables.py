#!/usr/bin/env python3
"""Generate the Q3 results tables for the thesis from the live Q3 CSVs.

Source of truth: fourarm/tables/ex2_q3/*.csv rebuilt 2026-09-02 11:58.
Output: <thesis>/tables/ex2_q3_*.tex, filenames derived from the \\label.
"""
import csv, os

# Resolved from this file rather than hardcoded, which pinned both to one
# machine. THESIS_REPO matches the variable ex1_reproduce_tables.ipynb uses.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "tables", "ex2_q3")
OUT = os.path.join(os.path.expanduser(
    os.environ.get("THESIS_REPO", "~/Desktop/msc-paper")), "tables")

MODELS = ["gpt_hi", "gemini", "claude_md"]
RUNGS = ["N0", "N-A", "N-C", "N-order", "N-D", "N-CD"]


def load(name):
    with open(os.path.join(SRC, "tab_ex2_q3_%s.csv" % name)) as f:
        return list(csv.DictReader(f))


def num(s):
    """Render a signed number for an S column: siunitx wants a plain minus."""
    v = float(s)
    if v == 0:
        v = 0.0
    return "%.1f" % v


def n(s):
    """Render a number for maths-mode inline use."""
    v = float(s)
    if v == 0:
        v = 0.0
    return "%.1f" % v


def ci(lo, hi):
    """Q1 house style: [$-21.6$, 11.2]; dagger when the interval is zero-width."""
    flo, fhi = float(lo), float(hi)
    if abs(flo - fhi) < 1e-9:
        return r"$\dagger$"
    def one(v):
        if v == 0:
            v = 0.0
        t = "%.1f" % v
        return "$%s$" % t if t.startswith("-") else t
    return "[%s, %s]" % (one(flo), one(fhi))


def mt(m):
    return r"\texttt{%s}" % m.replace("_", r"\_")


def rt(r):
    return r"\texttt{%s}" % r.replace("_", r"\_")


# --------------------------------------------------------------- Table 1
def ladder():
    rows = {(r["condition"], r["model"], r["rung"]): r for r in load("contrasts")}
    L = []
    A = L.append
    A(r"\begin{table}[H]")
    A(r"  \centering")
    A(r"  \small")
    A(r"  \setlength{\tabcolsep}{5pt}")
    A(r"  \begin{threeparttable}")
    A(r"    \caption{The paired contrast $\Delta$ at each instruction")
    A(r"      configuration, and its movement from the baseline \texttt{N0}. A")
    A(r"      positive $\Delta$ means the allocation changes with the resting")
    A(r"      face in the intended direction. Under \texttt{dims} the model must")
    A(r"      derive the opening from the scene; under \texttt{conflict\_face} the")
    A(r"      text states a face the image contradicts, so $\Delta=-100$ is")
    A(r"      complete text-following and $\Delta=+100$ complete image-following.")
    A(r"      The elicitation configuration \texttt{N-D} is additionally read")
    A(r"      against \texttt{N-order} in Table~\ref{tab:ex2:q3:attribution}.}")
    A(r"    \label{tab:ex2:q3:ladder}")
    A(r"    \begin{tabular}{@{}ll")
    A(r"        S[table-format=-3.1] c")
    A(r"        S[table-format=-3.1] c@{}}")
    A(r"      \toprule")
    A(r"      & & \multicolumn{2}{c}{Contrast $\Delta$ (pp)}")
    A(r"      & \multicolumn{2}{c}{Movement from \texttt{N0} (pp)} \\")
    A(r"      \cmidrule(lr){3-4} \cmidrule(lr){5-6}")
    A(r"      {Model} & {Configuration} & {$\Delta$} & {95\% CI}"
      r" & {$\Delta - \Delta_{\texttt{N0}}$} & {95\% CI} \\")
    for cond, title in [
        ("dims", r"\texttt{dims}: face and opening withheld, scene is the only source"),
        ("conflict_face", r"\texttt{conflict\_face}: text states the face the image contradicts"),
    ]:
        A(r"      \midrule")
        A(r"      \multicolumn{6}{@{}l}{%s} \\" % title)
        for mi, m in enumerate(MODELS):
            if mi:
                A(r"      \addlinespace")
            for ri, r in enumerate(RUNGS):
                row = rows.get((cond, m, r))
                if row is None:
                    continue
                lab = mt(m) if ri == 0 else ""
                if row["delta_vs_N0_pts"] == "-":
                    d, dci = "{--}", "{--}"
                else:
                    d = num(row["delta_vs_N0_pts"])
                    dci = ci(row["delta_lo"], row["delta_hi"])
                A(r"      %-18s & %-16s & %8s & %-18s & %8s & %s \\"
                  % (lab, rt(r), num(row["contrast_pts"]),
                     ci(row["contrast_lo"], row["contrast_hi"]), d, dci))
    A(r"      \bottomrule")
    A(r"    \end{tabular}")
    A(r"    \begin{tablenotes}[flushleft]\footnotesize")
    A(r"      \item \num{192} trials per cell (\num{32} positions $\times$ two")
    A(r"        resting faces $\times$ three repeats). \texttt{N0} is the")
    A(r"        baseline, so it has no movement column.")
    A(r"      \item[$\dagger$] Saturated: the same difference occurs at every")
    A(r"        position, so the paired interval collapses to zero width.")
    A(r"      \item Paired-$t$ intervals are not bounded by $\pm\num{100}$ and may")
    A(r"        extend past it when the contrast is near saturation.")
    A(r"    \end{tablenotes}")
    A(r"  \end{threeparttable}")
    A(r"\end{table}")
    return "\n".join(L)


# --------------------------------------------------------------- Table 2
def attribution():
    rows = load("attribution")
    idx = {(r["condition"], r["model"], r["contrast"]): r for r in rows}
    L = []
    A = L.append
    A(r"\begin{table}[H]")
    A(r"  \centering")
    A(r"  \small")
    A(r"  \begin{threeparttable}")
    A(r"    \caption{What the elicitation instruction adds once its two")
    A(r"      confounds are removed. \texttt{N-D} $-$ \texttt{N-order} holds the")
    A(r"      reordered output format constant, so the difference is the")
    A(r"      elicitation wording alone. \texttt{N-D} $-$ \texttt{N-C} reads")
    A(r"      elicitation against derivation, the other single-factor")
    A(r"      configuration. Values are mean within-position differences in")
    A(r"      $\Delta$ across the \num{32} positions.}")
    A(r"    \label{tab:ex2:q3:attribution}")
    A(r"    \begin{tabular}{@{}ll S[table-format=-3.1] c l@{}}")
    A(r"      \toprule")
    A(r"      {Model} & {Comparison} & {Difference (pp)} & {95\% CI} & {Reading} \\")
    for cond, title in [
        ("dims", r"\texttt{dims}"),
        ("conflict_face", r"\texttt{conflict\_face}"),
    ]:
        A(r"      \midrule")
        A(r"      \multicolumn{5}{@{}l}{%s} \\" % title)
        for m in MODELS:
            for k, lab in [("N-D_minus_N-order", r"\texttt{N-D} $-$ \texttt{N-order}"),
                           ("N-D_minus_N-C", r"\texttt{N-D} $-$ \texttt{N-C}")]:
                r = idx.get((cond, m, k))
                if r is None:
                    continue
                reading = "excludes zero" if r["reading"] == "positive" else "spans zero"
                A(r"      %-18s & %-34s & %8s & %-18s & %s \\"
                  % (mt(m) if k.endswith("order") else "", lab,
                     num(r["mean_pts"]), ci(r["paired_lo"], r["paired_hi"]), reading))
    A(r"      \bottomrule")
    A(r"    \end{tabular}")
    A(r"    \begin{tablenotes}[flushleft]\footnotesize")
    A(r"      \item[$\dagger$] Saturated: zero-width paired interval.")
    A(r"    \end{tablenotes}")
    A(r"  \end{threeparttable}")
    A(r"\end{table}")
    return "\n".join(L)


# --------------------------------------------------------------- Table 3
def reported():
    rows = {(r["condition"], r["model"], r["rung"], r["resting_face"]): r
            for r in load("reported")}
    L = []
    A = L.append
    A(r"\begin{table}[H]")
    A(r"  \centering")
    A(r"  \small")
    A(r"  \begin{threeparttable}")
    A(r"    \caption{Accuracy of the reported \texttt{opening\_needed\_m} under")
    A(r"      \texttt{dims}, by the face the object actually rests on. A reply")
    A(r"      counts as correct within \SI{6}{\milli\metre} of the opening the")
    A(r"      captured face implies. A model that reports the")
    A(r"      \texttt{small\_face} opening whatever the pose scores")
    A(r"      \SI{100}{\percent} on one row and \SI{0}{\percent} on the other.}")
    A(r"    \label{tab:ex2:q3:reported}")
    A(r"    \begin{tabular}{@{}ll S[table-format=3.1] c S[table-format=3.1] c@{}}")
    A(r"      \toprule")
    A(r"      & & \multicolumn{2}{c}{\texttt{small\_face} (\%)}"
      r" & \multicolumn{2}{c}{\texttt{large\_face} (\%)} \\")
    A(r"      \cmidrule(lr){3-4} \cmidrule(lr){5-6}")
    A(r"      {Model} & {Configuration} & {Correct} & {Wilson 95\% CI}"
      r" & {Correct} & {Wilson 95\% CI} \\")
    A(r"      \midrule")
    for mi, m in enumerate(MODELS):
        if mi:
            A(r"      \addlinespace")
        for ri, rg in enumerate(["N0", "N-C", "N-D", "N-CD"]):
            s = rows[("dims", m, rg, "small_face")]
            l = rows[("dims", m, rg, "large_face")]
            A(r"      %-18s & %-16s & %6s & [%s, %s] & %6s & [%s, %s] \\"
              % (mt(m) if ri == 0 else "", rt(rg),
                 n(s["correct_pct"]), n(s["wilson_lo"]), n(s["wilson_hi"]),
                 n(l["correct_pct"]), n(l["wilson_lo"]), n(l["wilson_hi"])))
    A(r"      \bottomrule")
    A(r"    \end{tabular}")
    A(r"    \begin{tablenotes}[flushleft]\footnotesize")
    A(r"      \item \num{96} replies per cell. \texttt{N-A} and \texttt{N-order}")
    A(r"        are omitted; neither moves any model away from its")
    A(r"        \texttt{N0} pattern.")
    A(r"    \end{tablenotes}")
    A(r"  \end{threeparttable}")
    A(r"\end{table}")
    return "\n".join(L)


# --------------------------------------------------------------- Table 4
def face():
    rows = {(r["condition"], r["model"], r["rung"]): r for r in load("face")}
    L = []
    A = L.append
    A(r"\begin{table}[H]")
    A(r"  \centering")
    A(r"  \small")
    A(r"  \begin{threeparttable}")
    A(r"    \caption{The resting face the model names, at the two configurations")
    A(r"      that require it to be stated before an arm is chosen. Correct means")
    A(r"      the face the image actually shows. The final column counts replies")
    A(r"      that name the correct face and then report an opening inconsistent")
    A(r"      with it, which separates a failure to read the pose from a failure")
    A(r"      to convert it.}")
    A(r"    \label{tab:ex2:q3:face}")
    A(r"    \begin{tabular}{@{}ll S[table-format=3.1] c S[table-format=3.0]@{}}")
    A(r"      \toprule")
    A(r"      {Model} & {Configuration} & {Correct face (\%)} & {Wilson 95\% CI}"
      r" & {Face right, opening wrong} \\")
    for cond, title in [
        ("dims", r"\texttt{dims}: no face is stated, so the image is uncontested"),
        ("conflict_face", r"\texttt{conflict\_face}: the text states the opposite face"),
    ]:
        A(r"      \midrule")
        A(r"      \multicolumn{5}{@{}l}{%s} \\" % title)
        for mi, m in enumerate(MODELS):
            for ri, rg in enumerate(["N-D", "N-CD"]):
                r = rows[(cond, m, rg)]
                A(r"      %-18s & %-16s & %6s & [%s, %s] & %3s \\"
                  % (mt(m) if ri == 0 else "", rt(rg),
                     n(r["correct_pct"]), n(r["wilson_lo"]), n(r["wilson_hi"]),
                     r["n_face_right_opening_wrong"]))
    A(r"      \bottomrule")
    A(r"    \end{tabular}")
    A(r"    \begin{tablenotes}[flushleft]\footnotesize")
    A(r"      \item \num{192} replies per cell, all of which named a face.")
    A(r"    \end{tablenotes}")
    A(r"  \end{threeparttable}")
    A(r"\end{table}")
    return "\n".join(L)


# --------------------------------------------------------------- Table 5
def directive():
    rows = load("directive")
    order = [
        ("headline", "conflict_face", "X-image", "N0",
         r"\texttt{X-image} $-$ \texttt{N0}"),
        ("sentence only", "conflict_face", "X-image", "N-A",
         r"\texttt{X-image} $-$ \texttt{N-A}"),
        ("control: wording", "congruent_face", "X-image", "N0",
         r"\texttt{X-image} $-$ \texttt{N0}"),
        ("control: symmetry", "conflict_face", "X-state", "N0",
         r"\texttt{X-state} $-$ \texttt{N0}"),
    ]
    heads = {
        "headline": r"The directive against the baseline, under \texttt{conflict\_face}",
        "sentence only": r"The precedence sentence alone, against \texttt{N-A}",
        "control: wording": r"Wording control: the same directive under "
                            r"\texttt{congruent\_face}, where the sources agree",
        "control: symmetry": r"Symmetry control: \texttt{conflict\_face} with the "
                             r"directive naming the text instead",
    }
    idx = {(r["read"], r["condition"], r["rung"], r["against"], r["model"]): r
           for r in rows}
    L = []
    A = L.append
    A(r"\begin{table}[H]")
    A(r"  \centering")
    A(r"  \small")
    A(r"  \begin{threeparttable}")
    A(r"    \caption{Movement in $\Delta$ under the two precedence directives.")
    A(r"      These are not configurations on the ladder: they name the stated")
    A(r"      face and tell the model which source wins, which the A, C and D")
    A(r"      factors deliberately do not. \texttt{X-image} is \texttt{N-A} plus")
    A(r"      the sentence \emph{where the image and the stated resting face")
    A(r"      disagree, go by the image}; \texttt{X-state} substitutes")
    A(r"      \emph{go by the state}. Positive movement is towards the image.}")
    A(r"    \label{tab:ex2:q3:directive}")
    A(r"    \begin{tabular}{@{}ll S[table-format=-3.1] c l@{}}")
    A(r"      \toprule")
    A(r"      {Model} & {Comparison} & {Movement (pp)} & {95\% CI} & {Reading} \\")
    for read, cond, rung, against, lab in order:
        A(r"      \midrule")
        A(r"      \multicolumn{5}{@{}l}{%s} \\" % heads[read])
        for m in MODELS:
            r = idx[(read, cond, rung, against, m)]
            reading = ("excludes zero" if r["interval"] == "excludes zero"
                       else "spans zero")
            A(r"      %-18s & %-30s & %8s & %-18s & %s \\"
              % (mt(m), lab, num(r["delta"]), ci(r["lo"], r["hi"]), reading))
    A(r"      \bottomrule")
    A(r"    \end{tabular}")
    A(r"    \begin{tablenotes}[flushleft]\footnotesize")
    A(r"      \item \num{128} trials per directive cell (\num{32} positions")
    A(r"        $\times$ two resting faces $\times$ two repeats), against")
    A(r"        \num{192} at \texttt{N0} and \texttt{N-A}.")
    A(r"      \item[$\dagger$] Saturated: zero-width paired interval.")
    A(r"      \item A movement of \num{200} points is a complete reversal, from")
    A(r"        $\Delta=-100$ to $\Delta=+100$.")
    A(r"    \end{tablenotes}")
    A(r"  \end{threeparttable}")
    A(r"\end{table}")
    return "\n".join(L)


# --------------------------------------------------------------- Table 6
def ceiling():
    ceil = {(r["model"], r["rung"]): r for r in load("ceiling")}
    con = {(r["condition"], r["model"], r["rung"]): r for r in load("contrasts")}
    cc = {r["model"]: r for r in load("ceiling_contrast")}
    L = []
    A = L.append
    A(r"\begin{table}[H]")
    A(r"  \centering")
    A(r"  \small")
    A(r"  \setlength{\tabcolsep}{5pt}")
    A(r"  \begin{threeparttable}")
    A(r"    \caption{The ceiling configuration \texttt{N-ACD} under")
    A(r"      \texttt{dims}, read against \texttt{N-CD}. \texttt{N-ACD} is")
    A(r"      \texttt{N-CD} plus the attention sentence and nothing else, so the")
    A(r"      difference between them is that sentence applied once derivation")
    A(r"      and elicitation are already in place. It bounds what instruction")
    A(r"      can achieve on this task, which separates a model that cannot")
    A(r"      derive the opening from one that was never asked for every step.}")
    A(r"    \label{tab:ex2:q3:ceiling}")
    A(r"    \begin{tabular}{@{}l")
    A(r"        S[table-format=-3.1] S[table-format=-3.1]")
    A(r"        S[table-format=-3.1] c")
    A(r"        S[table-format=3.1] S[table-format=3.1]@{}}")
    A(r"      \toprule")
    A(r"      & \multicolumn{2}{c}{Contrast $\Delta$ (pp)}")
    A(r"      & \multicolumn{2}{c}{Attention adds (pp)}")
    A(r"      & \multicolumn{2}{c}{Correct face (\%)} \\")
    A(r"      \cmidrule(lr){2-3} \cmidrule(lr){4-5} \cmidrule(lr){6-7}")
    A(r"      {Model} & {\texttt{N-CD}} & {\texttt{N-ACD}}"
      r" & {\texttt{N-ACD} $-$ \texttt{N-CD}} & {95\% CI}"
      r" & {\texttt{N-CD}} & {\texttt{N-ACD}} \\")
    A(r"      \midrule")
    for m in MODELS:
        c = cc[m]
        A(r"      %-18s & %6s & %6s & %6s & %-16s & %5s & %5s \\"
          % (mt(m),
             num(con[("dims", m, "N-CD")]["contrast_pts"]),
             num(c["contrast_pts"]),
             num(c["delta_vs_N-CD_pts"]),
             ci(c["delta_vs_N-CD_lo"], c["delta_vs_N-CD_hi"]),
             n(ceil[(m, "N-CD")]["face_correct_pct"]),
             n(ceil[(m, "N-ACD")]["face_correct_pct"])))
    A(r"      \bottomrule")
    A(r"    \end{tabular}")
    A(r"    \begin{tablenotes}[flushleft]\footnotesize")
    A(r"      \item \num{192} trials per cell. \texttt{N-ACD} was added on")
    A(r"        2026-09-01, after the six configurations of")
    A(r"        Table~\ref{tab:ex2:q3:ladder} had been run, and is not part of")
    A(r"        the pre-registered ladder.")
    A(r"      \item[$\dagger$] Saturated: zero-width paired interval.")
    A(r"      \item Run only in \texttt{dims}. In \texttt{conflict\_face} the")
    A(r"        same configuration would confound the procedure with")
    A(r"        precedence, which Table~\ref{tab:ex2:q3:directive} measures.")
    A(r"    \end{tablenotes}")
    A(r"  \end{threeparttable}")
    A(r"\end{table}")
    return "\n".join(L)


for fname, body in [("ex2_q3_ceiling", ceiling()),
                    ("ex2_q3_ladder", ladder()),
                    ("ex2_q3_attribution", attribution()),
                    ("ex2_q3_reported", reported()),
                    ("ex2_q3_face", face()),
                    ("ex2_q3_directive", directive())]:
    p = os.path.join(OUT, fname + ".tex")
    with open(p, "w") as f:
        f.write(body + "\n")
    print("wrote", p, len(body.splitlines()), "lines")
