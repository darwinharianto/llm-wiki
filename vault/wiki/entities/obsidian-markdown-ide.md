---
title: Obsidian Markdown IDE
slug: obsidian-markdown-ide
category: entities
aliases:
  - Obsidian
  - Markdown Vault
tags:
  - tooling
  - markdown
  - graph-view
sources:
  - 2026-04-karpathy-llm-wiki.md
created_at: 2026-04-02T11:15:00Z
updated_at: 2026-04-02T11:15:00Z
revision_count: 1
confidence: high
summary: Local-first Markdown workspace and graph viewer serving as the human reading IDE while the LLM acts as the wiki programmer.
---

# Obsidian Markdown IDE

In the [[llm-wiki-pattern|LLM Wiki Pattern]], the human does not manually maintain cross-references in a walled-garden database. Instead, the knowledge base lives as plain, Git-versioned Markdown files on disk: **Obsidian is the IDE; the LLM is the programmer; the wiki is the codebase.**

## Key Capabilities Leveraged

- **Bidirectional `[[wikilinks]]`**: Instant navigation between concept, entity, and source pages.
- **Interactive Graph View**: Reveals hubs, clusters, and orphan pages at a glance, complementing [[self-maintaining-knowledge-graphs|Self-Maintaining Knowledge Graphs]].
- **YAML Frontmatter**: Enables structured metadata (`tags`, `sources`, `revision_count`, `confidence`) for filtering and queries.
- **Git Version History**: Every LLM update or merge is auditable as a clean text diff.

