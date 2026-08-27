---
name: thesis-algorithm-style
description: >-
  Use whenever building, editing, or reviewing a pseudocode algorithm (an algorithm2e block) in the
  Marsh thesis, or when the user asks to add an algorithm, tidy one, or check that an algorithm reads
  clearly. Applies the agreed house style for the three appendix algorithms (Extraction / Retrieval /
  Commentary): line-numbered statements with grey "# comment" explanations, "Step N" headers, every
  symbol defined at first use, plain-English complete-thought comments, "human reviewer" for the
  person, and a build-render-verify recipe, so every algorithm reads as one family. The canonical
  reference is the Extraction algorithm appendix, *The Extraction Pipeline Algorithm*.
---

# Thesis algorithm style

The house style for every pseudocode algorithm in the thesis, so the appendices read as one family
and a non-expert can follow them. Use this whenever building, editing, or reviewing an algorithm,
even if not asked. Work in `thesis/` only. **The Extraction algorithm (*The Extraction Pipeline Algorithm*, `alg:extraction`)
is the canonical reference** — when in doubt, make the new algorithm look like it.

This style was settled through a long line-by-line review; the rules below are the fixes we agreed,
so apply them as house rules, not generic advice.

## Setup (already in `thesis/includes.tex` — reuse, don't redefine)
- `\usepackage[ruled,vlined,linesnumbered]{algorithm2e}` — **line numbering is on**: executable
  statements get a margin number, comment/step-header lines do not. This is what marks the numbered
  lines as algorithm *actions* (as in CLRS). Never turn it off.
- Comments are a **subtle grey italic** with a `#` marker (code-comment style):
  `\newcommand{\algcommentsty}[1]{\textcolor[gray]{0.40}{\textit{#1}}}`,
  `\SetKwComment{Comment}{\#\ }{}`, `\SetCommentSty{algcommentsty}`. The grey separates explanation
  from code and prints fine in mono.
- A long algorithm split across a page uses two `algorithm` environments with
  `\addtocounter{algocf}{-1}` (same algorithm number) **and** `\setcounter{AlgoLine}{<n>}` so the
  line numbers continue rather than restart — update `<n>` if the first page's line count changes.
  (the Extraction algorithm uses this; Retrieval does **not** — see the size note below.)
- **Font size.** Body is 11pt; algorithms are `\footnotesize` (≈9pt), the conventional one-to-two
  steps below body and the readable default. **Exception (27 Jul 2026):** the **Retrieval** algorithm
  is `\scriptsize` (≈8pt) as a **single merged environment** so it fits on one page — a deliberate
  choice (Yasmin's), accepted over strict size-parity with D/F. So Retrieval reads a touch smaller
  than Extraction/Commentary; do not "correct" it back to 9pt or re-split it in the name of the
  one-family rule. Extraction and Commentary stay 9pt.

## The intro paragraph (one, before the algorithm; nothing after it)
- Exactly **one paragraph before** the algorithm and **nothing after** it. Do not trail explanatory
  paragraphs after the environment — fold anything essential into the intro or the code comments.
- Open in the family pattern: `Algorithm~N presents the [extraction pipeline / retrieval procedure /
  commentary stage] of Section~\ref{...} (Figure~\ref{...})[, for a single amendment], [input -> output,
  or a referral to the human reviewer].` Use each stage's natural noun (pipeline / procedure / stage).
  **Do not say "control flow of"** — it reads as jargon; just name the pipeline/procedure/stage.
- Make the three read as **one pipeline in three parts**: the output term of one stage is the named
  input of the next (records -> cards -> comments), and each intro links back to the appendix that
  feeds it ("runs on the cards produced by the retrieval procedure of Appendix~E").
- Close with the deterministic-backbone + model-call note: "The backbone is deterministic code, and
  the lines marked (model) are the points at which an LLM is called." Only say **LLM** where it is
  accurate — Retrieval's `(model)` covers a classification LLM call *and* text-embedding-model calls,
  so it says so precisely rather than calling embeddings an LLM call.
- Keep it to ~2-3 sentences (match D and E). If one algorithm's intro balloons, trim it back.

## Comments (the `#` lines)
- **Every explanatory comment on its own line, left-aligned.** Reserve the **right-aligned trailing**
  comment (`\Comment*{...}`) only for the terse **`# model`** markers, so the model calls form a
  scannable column. Nothing else goes trailing-right.
- **One idea per comment.** Do not overload a comment with three things ("shortlist the ten, pull in
  linked amendments, then trim to five" -> split or simplify). If a gloss is doing two jobs (define a
  symbol *and* state a design point), split it into two comments.
- **Plain English, complete thoughts, no new terminology.** No cryptic fragments the reader has to
  unpack, and no jargon dropped in without explanation (kill "soft routing", "control flow"). Explain
  the *why* at key decisions, not every trivial line — comment the non-obvious (a guard, a fallback, a
  split), leave self-evident assignments alone.
- Comments should not be *inline parentheticals* in the code body. `x <- y (some note)` becomes
  `# some note` on its own line (or trailing only if it is `# model`). Genuine **definitions** stay
  inline (the three drafting headings; the KwIn glosses like `tau_c (above which ...)`).

## Notation (define at first use)
- **Every symbol is defined the first time it appears** — in `\KwIn`, or in a `#` comment on/before
  its line. A reader should never hit an undefined `topics(q)`, `conf`, `w`, `e_q`, `s(q,p)`, `v`,
  `supported`, etc. Do not rely on a gloss that appears *after* first use; move it up.
- Gloss **non-obvious named operations** once, briefly (`Repair` = "repair a broken file, then
  reconvert"); leave self-evident ones (`Convert`). Don't formally define standard maths.
- Keep it lean — inputs/outputs plus brief glosses on the non-obvious, leaning on the §3.2.x prose.
  Over-defining clutters; under-defining loses the reader. When unsure whether a symbol needs a
  gloss, add a short one.

## Canonical notation (the three share these — never diverge)
The same concept keeps the **same symbol** as it moves between algorithms; introduce a new symbol
only where the concept is genuinely new. The settled set (27 Jul 2026):

| Symbol | Meaning | Where |
|---|---|---|
| $q$ | one amendment (clause reference + proposed wording) | input to Retrieval and Commentary |
| $\mathcal{K}$ | the section / character-window chunks a large schedule is split into | Extraction, Step 3 |
| $c$ | a standard-form clause | Commentary |
| $\mathcal{C}$ | the five surrogate-labelled precedent cards | output of Retrieval, input to Commentary |

The review context is named **in words** in Extraction, not given a symbol (it dropped the old `c`,
which now belongs solely to Commentary's standard clause). Retrieval's card set was `\mathcal{R}`
and is now `\mathcal{C}`; Extraction's chunk set was `C` and is now `\mathcal{K}` — these removed a
symbol clash, so do not reintroduce either.

## Corpus vs knowledge base (distinct, nested terms)
- **Knowledge base** = the four-input grounding (standard-clause library, topic taxonomy, precedent
  corpus, review guidance). Use it **only** for that umbrella, never for the collection retrieval
  draws from.
- **Precedent corpus** = the 202 precedent records the commentary retrieves from, one of the four
  inputs. Name it "precedent corpus" at anchors (first mention, an input definition); use bare
  "corpus" for local repeats. Bare "corpus" is otherwise overloaded (generic ML/IR uses such as a
  "labelled corpus"), so "precedent corpus" reserves an unambiguous label.

## Machine vs person
- The only human actor is the **"human reviewer"** — always that phrase, never a bare "reviewer".
- Machine steps use **process names**, never person-like nouns: it is the **"validation check"**, not
  "the validator". Keep the distinction unmistakable so nobody reads a model step as a person.

## Lines and structure
- **Break an over-long statement into shorter numbered steps** rather than cramming two actions into
  one line (e.g. "rank two ways" and "fuse" become two lines). A flat run of operations reads as a
  numbered sequence, which is what line numbering makes clear — do not add manual "1./2./3." on top.
- Use `# Step N: ...` headers to group the stages, consistently across all three algorithms.

## Constants and future work
- **Every chosen constant needs a stated rationale/source** — a standard default *with a citation*
  (RRF rank constant 60, Cormack et al. 2009), a determined fact (N=202 = the curated corpus), or a
  design choice (R=2, the size thresholds). Flag provisional-to-calibrate values (beta, tau) as such.
  Do not present bare numbers. (Tracked as a to-do in `MORNING-NOTE.md` item 4.)
- **A feature deferred to future work must not appear as a live pipeline step.** If Future Work owns
  it (as with relationship expansion), remove it from the algorithm, reframe the §3.2.x mention as a
  forward-pointer, and drop any evaluation ablation of it — keep the story consistent across the
  algorithm, the design prose, future work, and the evaluation.

## Consistency across the three
- Sweep all three whenever a fix is made: the same wording, alignment, notation-definition and
  machine/person conventions apply to Extraction, Retrieval and Commentary alike.
- The hand-off terms, the `# model` marker meaning, the "human reviewer" phrasing and the "Step N"
  headers must match across the appendices.

## Build recipe (always render and eyeball)
1. Reuse the `includes.tex` setup; do not redefine the comment style inline.
2. Build with `latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex`; confirm **0 errors**
   (`grep -ciE '^! ' main.log`) and **0 undefined** references/citations.
3. **Render the algorithm's PDF page and read it** (find the page from `main.aux`). A clean build is
   not proof it reads right: check line numbers sit on statements (not comments), comments are grey
   and left-aligned (only `# model` right), every symbol is defined before use, and no comment is
   overloaded. Trailing comments on `\lIf`/`\lElse` lines are fragile — prefer an own-line comment
   before the line, or convert to an `\eIf` block.
4. Hand off to `thesis-ship` to build, check and sync — the file is edited in parallel in Overleaf,
   so always pull-rebase before pushing.

## Confidentiality
The usual hard line applies: no client-specific data in an algorithm or its comments. Naming a
generic input field ("the case details the human reviewer enters, such as the client and requestor
names") is fine; a real client, matter, or dataset is not. When unsure, run `confidentiality-check`.
