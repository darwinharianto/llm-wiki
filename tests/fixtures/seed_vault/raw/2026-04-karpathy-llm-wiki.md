# LLM Wiki — A Pattern for Persistent Personal Knowledge Bases

Author: Andrej Karpathy
Date: 2026-04-02
Source Type: Architecture Note

## Core Idea

Most people's experience with LLMs and documents looks like RAG: you upload a collection of files, the LLM retrieves relevant chunks at query time, and generates an answer. This works, but the LLM is rediscovering knowledge from scratch on every question. There is no accumulation.

Instead of just retrieving from raw documents at query time, the LLM incrementally builds and maintains a persistent wiki — a structured, interlinked collection of markdown files that sits between you and the raw sources. When you add a new source, the LLM reads it, extracts the key information, and integrates it into the existing wiki — updating entity pages, revising topic summaries, noting where new data contradicts old claims, strengthening or challenging the evolving synthesis.

## Three Layers

1. **Raw sources**: Immutable curated documents (articles, papers, data files). The LLM reads from them but never modifies them.
2. **The wiki**: Directory of LLM-generated markdown files (summaries, entity pages, concept pages, comparisons, syntheses).
3. **The schema**: A document (CLAUDE.md / AGENTS.md / SCHEMA.md) defining structure, conventions, and workflows for ingesting, querying, and linting.

## Operations

- **Ingest**: Drop a new source into raw/, read it, write/update summary, update index.md, update relevant entity and concept pages, append to log.md.
- **Query**: Search index.md and relevant pages, synthesize an answer with citations, and file good answers back into the wiki so explorations compound.
- **Lint**: Periodically health-check for contradictions, stale claims, orphan pages with no inbound links, missing concept pages, and missing cross-references.

