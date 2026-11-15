# Wiki Index

> Auto-maintained catalog of all compiled pages in `vault/wiki/`. Updated on every ingest, merge, edit, or lint pass.

_Total Pages: 9 | Concepts: 4 | Entities: 2 | Sources: 2 | Syntheses: 1_

## Concepts
- [[entity-deduplication-and-merging|Entity Deduplication and Merging]] — Policy and hybrid scoring mechanism that searches for similar existing wiki pages before creation and merges updates into canonical pages. *(tags: similarity-search, deduplication, merging | sources: 1 | rev: 1 | updated: 2026-05-10)*
- [[llm-wiki-pattern|LLM Wiki Pattern]] — Architectural pattern where an LLM incrementally builds and maintains a persistent, interlinked Markdown wiki instead of re-deriving answers via stateless RAG. *(tags: architecture, knowledge-base, llm-wiki | sources: 1 | rev: 2 | updated: 2026-05-10)*
- [[rag-vs-compiled-wiki|RAG vs Compiled Wiki]] — Comparison between stateless query-time chunk retrieval (RAG) and persistent, pre-compiled interlinked wiki knowledge bases. *(tags: rag, architecture, synthesis | sources: 2 | rev: 2 | updated: 2026-05-10)*
- [[self-maintaining-knowledge-graphs|Self-Maintaining Knowledge Graphs]] — Continuous automated linting and healing of wiki topology—converting unlinked mentions, resolving dangling links, integrating orphans, and tracking contradictions. *(tags: self-maintenance, knowledge-graph, linting | sources: 2 | rev: 2 | updated: 2026-11-13)*

## Entities
- [[obsidian-markdown-ide|Obsidian Markdown IDE]] — Local-first Markdown workspace and graph viewer serving as the human reading IDE while the LLM acts as the wiki programmer. *(tags: tooling, markdown, graph-view | sources: 1 | rev: 1 | updated: 2026-04-02)*
- [[vannevar-bush-memex|Vannevar Bush Memex]] — Vannevar Bush's 1945 conceptual personal knowledge store built around associative trails, whose missing maintenance layer is solved by LLMs. *(tags: history, hypertext, associative-trails | sources: 2 | rev: 1 | updated: 2026-04-02)*

## Sources
- [[source-as-we-may-think|Source: As We May Think]] — Distilled summary of Vannevar Bush's 1945 essay introducing associative indexing and the Memex personal knowledge device. *(tags: primary-source, memex, history | sources: 1 | rev: 2 | updated: 2026-11-13)*
- [[source-karpathy-llm-wiki|Source: Karpathy LLM Wiki]] — Primary source note distilling Andrej Karpathy's 2026 LLM Wiki pattern, three-layer architecture, and Ingest/Query/Lint workflows. *(tags: primary-source, llm-wiki | sources: 1 | rev: 1 | updated: 2026-04-02)*

## Syntheses
- [[compounding-knowledge-architecture|Compounding Knowledge Architecture]] — Master synthesis uniting Karpathy's LLM Wiki, similarity-first entity merging, autonomous graph linting, and Bush's Memex into an ever-evolving system. *(tags: synthesis, architecture, knowledge-base | sources: 3 | rev: 1 | updated: 2026-05-10)*
