# Beyond Stateless RAG: Compiled Knowledge Systems

Author: Research Notes
Date: 2026-05-10
Source Type: Technical Synthesis

## Why Stateless RAG Plateaus

Standard Retrieval-Augmented Generation (RAG) treats a document corpus as a passive bag of chunks. Every complex question forces the model to re-discover relationships, re-reconcile terminology, and re-synthesize contradictions from fragmented passages.

## Compiled Wiki Advantages

1. **Pre-computed Synthesis**: Cross-document comparisons and entity timelines are compiled once during ingest and kept current.
2. **Entity Deduplication**: Before creating a new knowledge artifact, a self-maintaining system searches for similar existing entities or concepts and updates the canonical page rather than spawning redundant fragments.
3. **Graph Topology as Signal**: Tracking inbound links, hub nodes, and orphan pages reveals structural blind spots in a user's understanding.
4. **Automated Contradiction Detection**: New evidence either strengthens existing claims or explicitly annotates tensions alongside older sources.

