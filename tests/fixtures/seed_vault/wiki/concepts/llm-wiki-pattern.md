---
title: LLM Wiki Pattern
slug: llm-wiki-pattern
category: concepts
aliases:
  - Karpathy LLM Wiki
  - Compiled Personal Wiki
tags:
  - architecture
  - knowledge-base
  - llm-wiki
sources:
  - 2026-04-karpathy-llm-wiki.md
created_at: 2026-04-02T10:00:00Z
updated_at: 2026-05-10T14:30:00Z
revision_count: 2
confidence: high
summary: Architectural pattern where an LLM incrementally builds and maintains a persistent, interlinked Markdown wiki instead of re-deriving answers via stateless RAG.
---

# LLM Wiki Pattern

The **LLM Wiki Pattern**, popularized by Andrej Karpathy in [[source-karpathy-llm-wiki|LLM Wiki (2026)]], shifts AI knowledge management from query-time rediscovery to continuous compilation.

## Core Thesis

Rather than leaving raw documents untouched and retrieving disconnected chunks at query time (see [[rag-vs-compiled-wiki|RAG vs Compiled Wiki]]), an LLM agent sits between the human curator and the source collection. Every new source is read, distilled, cross-referenced, and integrated into existing topic pages.

## The Three Layers

1. **Raw Sources (`raw/`)**: Immutable primary artifacts curated by the human.
2. **The Wiki (`wiki/`)**: LLM-owned Markdown pages covering concepts, entities, source summaries, and syntheses.
3. **The Schema (`SCHEMA.md`)**: Explicit operating instructions defining page formats, linking rules, and maintenance workflows.

## Why Maintenance Scales

Human-run wikis collapse when bookkeeping (updating cross-references, merging overlapping notes, resolving contradictions) outpaces value. Because an LLM can inspect dozens of pages in seconds, [[self-maintaining-knowledge-graphs|Self-Maintaining Knowledge Graphs]] turn maintenance cost near zero.

## Evolution & Synthesized Updates

- **[2026-05-10]** Enriched with insights from `2026-05-rag-vs-persistent-synthesis.md`: formalized [[entity-deduplication-and-merging|Entity Deduplication and Merging]] as a mandatory pre-create step during ingest so knowledge compounds into canonical pages rather than fragmenting.
- Connects historically to [[vannevar-bush-memex|Vannevar Bush's Memex]], which envisioned associative trails without an automated archivist.

