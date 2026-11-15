# LLM Wiki Schema

> **Pattern**: Persistent, compounding, self-maintaining personal knowledge base inspired by Andrej Karpathy's [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) architecture.

## 1. Three-Layer Architecture

1. **Raw Sources (`vault/raw/`)**: Immutable source of truth (articles, papers, notes, transcripts). The LLM reads from `raw/` and **never modifies** files in `raw/`.
2. **Compiled Wiki (`vault/wiki/`)**: LLM-owned Markdown pages organized into:
   - `concepts/` — Core ideas, mental models, architectural patterns, methodologies.
   - `entities/` — People, systems, tools, organizations, historical artifacts.
   - `sources/` — Structured distilled summaries of ingested raw documents.
   - `syntheses/` — Cross-cutting comparisons, analyses, and filed chat explorations.
3. **The Schema (`vault/SCHEMA.md`)**: This living specification governing conventions, workflows, and invariants.

## 2. Page Format & YAML Frontmatter

Every wiki page MUST start with valid YAML frontmatter:

```yaml
---
title: Human-Readable Page Title
slug: kebab-case-slug
category: concepts # concepts | entities | sources | syntheses
aliases:
  - Alternate Name
tags:
  - knowledge-base
  - llm-wiki
sources:
  - 2026-04-karpathy-llm-wiki.md
created_at: 2026-04-02T10:00:00Z
updated_at: 2026-04-02T10:00:00Z
revision_count: 1
confidence: high # high | medium | evolving
summary: One-line summary for index.md and rapid retrieval.
---
```

### Cross-Referencing Conventions

- Use Obsidian-compatible wikilinks: `[[slug]]` or `[[slug|Display Text]]`.
- Every page should link to at least 2 related pages and have inbound links (zero orphans).
- Keep claims grounded in `sources` and explicitly document disagreements under `## Contradictions & Tensions`.

## 3. Core Workflows

### Workflow A: Similarity-First Ingest (Update Instead of Create)

Whenever a new source or note arrives:
1. Archive the immutable raw document in `vault/raw/<YYYY-MM-DD>-<slug>.md`.
2. Extract candidate topics, entities, and claims.
3. **Mandatory Similarity Search**: Run the Hybrid Similarity Engine (Title/Alias overlap + BM25 + TF-IDF n-gram cosine + Concept/Tag Jaccard) against all existing pages in `vault/wiki/`.
4. **Update Instead of Duplicate**:
   - If an existing page scores `>= similarity_threshold` (default `0.35`), **update the existing page in-place** rather than creating a new page.
   - Preserve prior synthesis, integrate new insights into `## Evolution & Synthesized Updates`, flag any diverging claims in `## Contradictions & Tensions`, merge `tags`/`aliases`/`sources`, increment `revision_count`, and store a unified diff snapshot in `vault/.history/<slug>.json`.
   - Only create a new wiki page when no existing page exceeds the threshold.
5. Rebuild `vault/index.md` and append an entry to `vault/log.md`.
6. Run post-ingest self-maintenance to heal new unlinked mentions.

### Workflow B: Grounded Query & File-to-Wiki

1. Read `vault/index.md` and execute Hybrid Search over `vault/wiki/` to retrieve the most relevant pages.
2. Synthesize an answer citing pages with `[[slug|Title]]` wikilinks.
3. If the answer produces a valuable synthesis, comparison, or insight, **file it back into the wiki** via Workflow A (searching for an existing similar synthesis/concept page to update first!).

### Workflow C: Autonomous Self-Maintenance (Lint & Auto-Heal)

Periodically and after major ingests, audit the vault for:
- **Unlinked Mentions**: Plain-text references to another page's title or alias -> convert to `[[slug|mention]]`.
- **Orphan Pages**: Pages with 0 inbound links -> weave links from topically closest hub pages.
- **Dangling Wikilinks**: `[[missing]]` links -> resolve to a high-similarity existing page or synthesize a new stub concept page.
- **Near-Duplicate Pages**: Pairs of pages with high overlap -> flag or merge cleanly while redirecting all inbound links.
- **Contradictions & Stale Claims**: Highlight conflicting claims across sources.
- **Index & Frontmatter Drift**: Ensure `vault/index.md` and YAML frontmatter stay synchronized.

## 4. Navigation & Audit Files

- `vault/index.md`: Content-oriented catalog grouped by category, updated on every write.
- `vault/log.md`: Append-only chronological record formatted as `## [YYYY-MM-DD HH:MM] <operation> | <Title>`.

