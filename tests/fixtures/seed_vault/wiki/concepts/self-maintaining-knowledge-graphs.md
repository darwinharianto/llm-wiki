---
title: Self-Maintaining Knowledge Graphs
slug: self-maintaining-knowledge-graphs
category: concepts
aliases:
- Autonomous Wiki Linting
- Self-Healing Knowledge Base
tags:
- self-maintenance
- knowledge-graph
- linting
sources:
- 2026-04-karpathy-llm-wiki.md
- 2026-05-rag-vs-persistent-synthesis.md
created_at: '2026-04-03 09:00:00+00:00'
updated_at: '2026-11-13T17:37:21Z'
revision_count: 2
confidence: high
summary: Continuous automated linting and healing of wiki topology—converting unlinked
  mentions, resolving dangling links, integrating orphans, and tracking contradictions.
---

# Self-Maintaining Knowledge Graphs

A core requirement of an [[compounding-knowledge-architecture|ever-evolving knowledge base]] is that it repairs and strengthens its own topology as new information arrives, rather than degrading into disconnected notes.

## Six Health Dimensions

1. **Unlinked Mentions**: Detecting plain-text references to existing concepts (for example, mentioning Obsidian Markdown IDE without linking it) and weaving `[[wikilinks]]`.
2. **Orphan Detection**: Identifying pages with zero inbound links and connecting them to relevant hub pages such as [[llm-wiki-pattern|LLM Wiki Pattern]].
3. **Dangling Link Resolution**: Finding `[[targets]]` that do not yet exist and either pointing them to a close existing page via [[entity-deduplication-and-merging|Entity Deduplication and Merging]] or creating a stub concept page.
4. **Near-Duplicate Consolidation**: Merging overlapping pages into a single canonical synthesis.
5. **Contradiction & Stale-Claim Auditing**: Highlighting conflicting evidence across newer and older sources.
6. **Index & Log Synchronization**: Keeping `index.md` and `log.md` synchronized with every mutation.

## Graph Topology as Cognitive Signal

In tools like [[obsidian-markdown-ide|Obsidian Markdown IDE]], force-directed graph views expose structural patterns: dense hubs reveal core pillars of understanding, while isolated clusters or orphans highlight blind spots ripe for further research.
