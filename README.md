# LLM Wiki — Ever-Evolving, Self-Maintaining Knowledge Base

An implementation of [Andrej Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern featuring **Similarity-First Ingest (Update Instead of Create)**, **Autonomous Self-Maintenance (Lint & Auto-Heal)**, an **Interactive Force-Directed Knowledge Graph**, and **Grounded Multi-Turn Wiki Chat** with **File-to-Wiki** compounding synthesis.

## Architecture (3 Layers)

1. **`vault/raw/` (Immutable Raw Sources)** — Original articles, papers, and clippings. Never modified by the LLM.
2. **`vault/wiki/` (LLM-Owned Compiled Wiki)** — Interlinked Markdown pages with YAML frontmatter and `[[wikilinks]]` organized into `concepts/`, `entities/`, `sources/`, and `syntheses/`, plus `vault/index.md`, `vault/log.md`, and `vault/.history/` revision diffs.
3. **`vault/SCHEMA.md` (The Schema)** — Rules and workflows governing ingestion, similarity-first updating, cross-referencing, contradictions tracking, and self-maintenance.

## Quick Start

```bash
# 1. Activate the virtual environment
source .venv/bin/activate

# 2. Run the FastAPI server
uvicorn backend.app:app --host 127.0.0.1 --port 8000

# 3. Open http://127.0.0.1:8000 in your browser
```

### Optional LLM Providers

Out of the box, the system runs with a **Smart Offline Synthesis** engine (`local_smart`) so ingestion, similarity matching, self-maintenance, and chat work immediately without external API keys. You can configure **Gemini** (`GEMINI_API_KEY`, using `google-genai` Interactions API with `gemini-4-hydrogen`), **OpenAI-compatible** (`OPENAI_API_KEY`), or **Ollama** (`OLLAMA_BASE_URL`) at runtime via the Settings dialog or environment variables.

## Running Tests

```bash
.venv/bin/pytest tests/test_wiki_system.py -v
```

