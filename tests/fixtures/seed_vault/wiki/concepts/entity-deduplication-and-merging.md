---
title: Entity Deduplication and Merging
slug: entity-deduplication-and-merging
category: concepts
aliases:
  - Similarity-First Update
  - Update Instead of Create
tags:
  - similarity-search
  - deduplication
  - merging
sources:
  - 2026-05-rag-vs-persistent-synthesis.md
created_at: 2026-05-10T14:00:00Z
updated_at: 2026-05-10T14:45:00Z
revision_count: 1
confidence: high
summary: Policy and hybrid scoring mechanism that searches for similar existing wiki pages before creation and merges updates into canonical pages.
---

# Entity Deduplication and Merging

Without active deduplication, an automated knowledge base quickly fractures into dozens of near-identical pages (`karpathy-wiki.md`, `llm-wiki-notes.md`, `persistent-ai-wiki.md`), destroying the compounding value of [[compounding-knowledge-architecture|Compounding Knowledge Architecture]].

## Similarity-First Update Policy

Before writing any new page during ingest or chat-to-wiki filing, the system runs a **Hybrid Similarity Search** across all existing pages in `vault/wiki/`:

1. **Title, Slug & Alias Overlap**: Token and fuzzy matching against page titles and frontmatter `aliases`.
2. **BM25 Lexical Relevance**: Weighted term frequency across titles, summaries, tags, and prose.
3. **N-Gram TF-IDF Cosine Similarity**: Captures topical and phrased similarity even when titles differ.
4. **Graph & Tag Jaccard**: Measures shared `tags` and `[[wikilinks]]`.

## Update Instead of Build New

When the composite similarity score meets or exceeds the configured threshold:
- **No duplicate file is created.**
- New insights, claims, and source citations are woven into the existing canonical page.
- A revision diff is recorded in `.history/` and `revision_count` increments.
- Any conflicting claims are documented explicitly rather than silently overwriting history, supporting [[self-maintaining-knowledge-graphs|Self-Maintaining Knowledge Graphs]].

