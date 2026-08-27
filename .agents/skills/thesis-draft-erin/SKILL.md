---
name: thesis-draft-erin
description: "A thesis-focused writing and review workflow that combines clear academic prose with rigorous scientific and methodological judgement. It guides drafting, revision, appendices, algorithms, results, tables, and figures while preserving the thesis's established terminology, scope, and research logic. It also checks that claims are evidence-based, methods support the research questions, and results are presented accurately without overclaiming."
---

# Thesis drafting workflow

How to take a thesis section from idea to a clean, rigorous draft. This skill owns the **writing and judgement**. Mechanical build, repository management, and other tooling should be handled separately when needed.

## 1. Load context first

Before drafting or substantially revising a section, gather the relevant project context so that the section remains consistent with the rest of the thesis:

* Review the current thesis/project context and previously established methodological decisions.
* Check the intended structure and role of the section within the thesis.
* Identify relevant research questions, hypotheses, experimental objectives, and scope.
* Check known open questions, unresolved decisions, and methodological limitations.
* Use the most recent and authoritative project information when earlier decisions have been superseded.
* Do not invent missing information. Flag anything that needs confirmation.

When relevant, inspect the current thesis source and supporting materials before making substantive changes.

## 2. Draft or edit

* Edit the relevant thesis source files directly when requested.
* Treat the document as a **thesis** unless the user explicitly uses another term for a specific purpose.
* Preserve the established terminology, experimental framing, and scope unless there is a clear reason to recommend a change.
* Synthesise information from the available project context, credible sources, and established research knowledge.
* Never fabricate statistics, experimental results, citations, methodological details, or implementation facts.
* For claims requiring evidence, identify what supports the claim and flag missing evidence.
* When a methodological choice is questionable, explain the issue and recommend a stronger alternative rather than silently changing it.
* Distinguish clearly between:

  * established facts,
  * results supported by the data,
  * methodological decisions,
  * interpretations,
  * limitations,
  * and recommendations.

## 3. House style

Write in a clear, concise, academically appropriate student register.

### Core rules

* Prefer plain English over unnecessarily sophisticated vocabulary.
* Keep sentences reasonably short and information-dense.
* Define technical terms on first use where necessary.
* Maintain consistent terminology throughout the thesis.
* Use a measured, precise tone.
* Avoid unnecessary hedging.
* Justify methodological decisions explicitly, using the structure **"X over Y because Z"** where appropriate.
* Do not overstate what the evidence demonstrates.
* Keep descriptions proportional to their importance.
* Remove repetition between adjacent sections.
* Ensure every paragraph has a clear purpose.

### Avoid common AI-writing patterns

Avoid generic or inflated wording such as:

* "leverage"
* "robust"
* "seamless"
* "delve"
* "crucial"
* "landscape"
* "pivotal"
* "underscore"

Also avoid:

* formulaic rhetorical questions;
* unnecessary three-part rhetorical lists;
* exaggerated claims;
* "not just X but Y" constructions;
* generic introductory filler;
* vague claims such as "this highlights the importance of..." without specifying what the result actually shows.

Follow any explicit formatting or style constraints established for the thesis.

## 3b. Appendices

Appendices should be **self-contained but supplementary**. They should provide operational or technical detail without re-arguing the main thesis.

When drafting or reviewing an appendix:

* Reference the appendix from the main text at least once.
* Open with a brief sentence explaining what the appendix contains and which section or component it supports.
* Include definitions or reading conventions that a reader needs to understand the appendix.
* Include precise operational details that are useful for reproducibility but unnecessary in the main text.
* Do not unnecessarily repeat figures, tables, arguments, or explanations already presented in the body.
* Cross-reference the main text where repetition would otherwise occur.

The test is:

> Could a reader understand the appendix on its own, and does it provide additional detail rather than simply repeat the main argument?

## 3c. Algorithms

When the thesis uses `algorithm2e`, apply the established algorithm formatting consistently across all algorithms.

* Use the thesis's configured `algorithm2e` environment and formatting.
* Use consistent indentation, spacing, captions, labels, and notation.
* Clearly identify model/LLM calls where relevant.
* Use readable section or phase markers for logically distinct parts of an algorithm.
* Include a short introductory paragraph explaining what the algorithm does and how it relates to the surrounding section.
* Do not re-derive the methodology in the algorithm if it has already been explained in the main text.
* If an algorithm is too long to fit on one page, split it into logically coherent parts while preserving numbering and cross-references.

The exact LaTeX implementation should follow the conventions already established in the thesis source.

## 4. Scientific and methodological judgement

The primary goal is not merely polished prose. The section must be **scientifically defensible**.

When reviewing a section:

1. Check whether the claims follow from the evidence.
2. Check whether the methodology actually supports the stated research question.
3. Check whether important assumptions are explicit.
4. Check whether comparisons are fair and interpretable.
5. Check whether tables and figures communicate the intended evidence.
6. Check whether terminology accurately reflects what was measured.
7. Check whether limitations are acknowledged where they materially affect interpretation.
8. Check whether any analysis is missing that is necessary to support a central claim.
9. Distinguish genuine methodological problems from issues that are primarily matters of presentation.
10. Prefer the simplest defensible explanation and analysis over unnecessary complexity.

Do not agree with a proposed approach simply because it was previously chosen. If a decision is weak, explain why and suggest a better alternative. At the same time, do not introduce problems merely for the sake of criticism.

When multiple approaches are defensible, explain the main trade-off and recommend one.

## 5. Results, tables, and figures

For experimental sections, treat the results presentation as part of the scientific argument.

Check that:

* every reported number can be traced to the underlying data;
* sample sizes and units are clear;
* statistical summaries are appropriate for the outcome type;
* uncertainty is reported where appropriate;
* comparisons correspond to the experimental design;
* tables do not contain redundant information;
* figures highlight the scientifically important patterns;
* captions are sufficiently informative to interpret the figure;
* terminology is consistent between text, tables, figures, and analysis scripts;
* the Results section separates observation from interpretation;
* negative or null results are reported as findings rather than treated as failures;
* conclusions do not exceed what the experiment can establish.

Never invent or estimate a missing statistic. Mark unresolved values explicitly and identify what needs to be calculated or verified.

## 6. Section-level structure

For each section, check the logical progression:

**Motivation → Objective → Method → Evidence → Result → Interpretation → Limitation**

Not every section needs every component explicitly, but the reader should always understand:

* why the section exists;
* what question it addresses;
* what was done;
* what was measured;
* what was found;
* and what the finding means.

Avoid moving methodological details into Results or interpretation into Method unless there is a clear structural reason.

## 7. Revision process

When revising an existing section:

1. First understand what the current version is trying to accomplish.
2. Identify substantive methodological or logical problems.
3. Identify clarity and structure problems.
4. Identify unnecessary material.
5. Propose changes before making major structural changes when the user's decision is needed.
6. Preserve correct material rather than rewriting everything unnecessarily.
7. After revision, check consistency with the surrounding thesis.
8. Check that no previously established result, qualification, or limitation has been accidentally removed.

When the user asks for brainstorming or diagnosis rather than rewriting, **do not rewrite automatically**. First explain the issues and proposed improvements.

## 8. Report back

When reviewing or revising a section, keep feedback structured and actionable.

Prioritise:

1. **Critical issues** that affect scientific validity.
2. **Important issues** that affect clarity or interpretation.
3. **Optional improvements** that improve presentation but are not necessary.

End with a short **For your input** section containing only decisions, unresolved questions, missing information, or calculations that require the user's input.

Do not bury important methodological concerns under stylistic suggestions.