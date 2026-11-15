---
title: RAG vs Compiled Wiki
slug: rag-vs-compiled-wiki
category: concepts
aliases:
- Stateless RAG vs Wiki
- Compiled Knowledge vs Retrieval
tags:
- rag
- architecture
- synthesis
sources:
- 2026-04-karpathy-llm-wiki.md
- 2026-05-rag-vs-persistent-synthesis.md
created_at: '2026-04-02 10:15:00+00:00'
updated_at: '2026-11-14T05:19:05Z'
revision_count: 3
confidence: high
summary: Comparison between stateless query-time chunk retrieval (RAG) and persistent,
  pre-compiled interlinked wiki knowledge bases.
---

# RAG vs Compiled Wiki

Standard Retrieval-Augmented Generation (RAG) and the [[llm-wiki-pattern|LLM Wiki Pattern]] represent two fundamentally different approaches to interacting with personal or team document collections.

## Structural Comparison

| Dimension | Stateless RAG | Compiled LLM Wiki |
| :--- | :--- | :--- |
| **Knowledge state** | Passive bag of vector chunks | Active, interlinked Markdown graph |
| **Synthesis timing** | Re-derived from scratch on every query | Pre-compiled at ingest and continuously updated |
| **Cross-references** | Implicit via vector similarity | Explicit `[[wikilinks]]` and backlink trails |
| **Contradiction handling** | Often missed or silently blended | Explicitly flagged in page tension sections |
| **Query compounding** | Answers vanish into chat history | Insights can be filed back into [[compounding-knowledge-architecture|Compounding Knowledge Architecture]] |

## When Stateless RAG Fails

When a subtle question spans five distinct documents, stateless RAG must rediscover terminology alignment and resolve conflicting claims from scratch every single time. Over months of research, nothing accumulates.

## Contradictions & Tensions

- **Upfront vs. Lazy Cost**: Stateless RAG minimizes ingest cost (just chunk and embed) while paying synthesis cost repeatedly at query time. Compiled wikis pay a small structured update cost at ingest, making subsequent queries faster, deeper, and cumulative. Hybrid local search (BM25 + TF-IDF + link graph) bridges both worlds inside [[self-maintaining-knowledge-graphs|Self-Maintaining Knowledge Graphs]].

## Related Concepts

- Related trail: [[3gpp-21915-f00-numerologies-waveform-and-frame-structure|3GPP 21915-f00: Numerologies, waveform and frame structure]] — 5.5.4.1	Numerologies, waveform and frame structure Similar to LTE, OFDM with Cyclic Prefix (CP) is used as the downlink (DL) waveform for NR. In contrast to LTE, OFDM can also b...
