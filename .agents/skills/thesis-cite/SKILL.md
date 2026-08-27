---
name: thesis-cite
description: >-
  Use whenever a claim needs a source, when choosing the best source for a point, or when
  checking that a paper or source actually exists. Reach for it even if not explicitly asked,
  because an unverified or hallucinated reference is a serious error. Finds, verifies, and formats
  a citation for the Marsh thesis using the source-credibility hierarchy, checks the Zotero library
  first and saves verified sources back into it, verifies the source is real via Crossref or the
  primary page, checks recency and standing, and outputs a Vancouver-style BibTeX entry plus the
  cite key.
---

# Thesis citation: find, verify, format, file in Zotero

This is an academic thesis, so every citation must be the most credible available and
must be real. Verifying is not optional: a hallucinated reference is a serious error.

Zotero is the library of record. Look there before searching the web, and put every
verified source back there so the library stays complete.

## 0. Check Zotero first
Before any web search, search the library for the claim's topic with
`zotero_semantic_search`, falling back to `zotero_search_items` if the semantic index is
not built. If a suitable item is already there:
- use it, pull its metadata with `zotero_get_item_metadata` rather than re-deriving it,
  and skip to step 3;
- only look further afield if the library item is weaker than the hierarchy in step 1
  demands, or is out of date.

Tool names may carry a client prefix such as `mcp__remote-devices__zotero__`. Match on the
`zotero_` part. If no Zotero tool is present in this session, carry on without it and say
once, at the end, that the source was not filed because Zotero was not reachable.

## 1. Find the most credible source (hierarchy)
1. Most preferred: peer-reviewed papers; official statistics and government sources (ONS,
   legislation.gov.uk); recognised standards, professional, or issuing bodies (RIBA, JCT,
   BSI).
2. Acceptable fallback: reputable secondary analyses (e.g. established law firms).
3. Avoid where a better source exists: general blogs, company marketing, unattributed web
   pages.

Prefer primary over secondary (cite the actual report or survey, not a blog summarising
it). Prefer recent. Match the claim to what the source actually says, and never
mischaracterise a figure or its scope.

## 2. Verify it is real (quadruple-check)
Confirm the source exists before relying on it:
- For a DOI: fetch `https://api.crossref.org/works/<DOI>` and check title, authors,
  journal, year, and pages.
- By title: `https://api.crossref.org/works?query.bibliographic=<title>&rows=3`.
- Or fetch the publisher or primary page. If a page is paywalled or redirects to an auth
  wall, verify via Crossref instead, and do not invent details you cannot confirm.
- If you cannot confirm it exists, do not use it, and say so.

## 3. Check standing and recency
Where it matters, note the journal's standing (for example its SJR quartile) and flag a
low-tier or dated source so the user can decide. Prefer the most up-to-date version.

## 4. Save it to Zotero
Only after step 2 passes. Never add an unverified source to the library.

Add with `zotero_add_item`:
- Always pass the DOI as `source` when there is one, because that route pulls clean
  metadata from Crossref. Fall back to a stable primary URL (report PDF, legislation page,
  standards page), then to the BibTeX from step 5.
- Set `if_exists='file'` so a source already in the library is reused and simply filed,
  never duplicated.
- Pass `collections` and `tags` in the same call rather than filing afterwards.
- Leave `attach_mode='auto'` so an open-access PDF comes down with the item.

Filing rules:
- Resolve the target collection with `zotero_search_collections` first, and pass its key.
- Chapter work goes in the matching subcollection under `Dissertation`, for example
  `Dissertation/Litreature Review`.
- If the chapter is unclear, file at `Dissertation` and say so in the output.
- Leave `create_missing_collections` at False. If a chapter collection does not exist yet,
  ask before creating it with `zotero_create_collection`. Do not invent folder structure.
- Tag with the thesis theme the source supports, short and lowercase, for example
  `retrieval`, `procurement`, `evaluation`.
- To refile an item that is already in the library, use `zotero_set_item_collections`.
- After adding, call `zotero_update_search_database` so semantic search sees the new item.

Keep the Zotero citation key and the BibTeX key the same wherever possible, so
`thesis/references.bib` and the library stay aligned.

## 5. Output
- A BibTeX entry for `thesis/references.bib`, Vancouver-style numeric (natbib).
- The `\citep{key}` or `\cite{key}` to drop into the text.
- A one-line basis note: what the recommendation rests on, and any gaps or caveats.
- One line on Zotero: added to which collection, already present, or not filed and why.

## 6. Flag
If a source's credibility or currency is doubtful, flag it to the user rather than
quietly using it. Cite credibly, or not at all.
