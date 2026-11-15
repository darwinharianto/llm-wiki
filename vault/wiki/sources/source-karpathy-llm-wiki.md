---
title: "Source: Karpathy LLM Wiki"
slug: source-karpathy-llm-wiki
category: sources
aliases:
  - Karpathy Gist
tags:
  - primary-source
  - llm-wiki
sources:
  - 2026-04-karpathy-llm-wiki.md
created_at: 2026-04-02T10:05:00Z
updated_at: 2026-04-02T10:05:00Z
revision_count: 1
confidence: high
summary: Primary source note distilling Andrej Karpathy's 2026 LLM Wiki pattern, three-layer architecture, and Ingest/Query/Lint workflows.
---

# Source: Karpathy LLM Wiki

- **Raw File**: `vault/raw/2026-04-karpathy-llm-wiki.md`
- **Author**: Andrej Karpathy
- **Core Contribution**: Proposes replacing stateless query-time RAG with an LLM-maintained persistent Markdown wiki.

## Key Takeaways

1. **Knowledge Compounds**: Summaries, entity pages, and cross-references are compiled once and updated incrementally rather than rediscovered per prompt.
2. **Three Operations**: **Ingest** (read source -> update wiki/index/log), **Query** (synthesize from wiki & file good answers back), and **Lint** (health-check for contradictions, orphans, and stale claims).
3. **Human-LLM Division of Labor**: The human curates sources and asks questions; the LLM handles bookkeeping across [[llm-wiki-pattern|LLM Wiki Pattern]] and [[obsidian-markdown-ide|Obsidian Markdown IDE]].
4. **Historical Lineage**: Draws direct inspiration from [[vannevar-bush-memex|Vannevar Bush's Memex]].

