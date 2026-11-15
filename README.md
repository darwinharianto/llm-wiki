# LLM Wiki — Ever-Evolving, Self-Maintaining Knowledge Base

An implementation of [Andrej Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern featuring **Similarity-First Ingest (Update Instead of Create)**, **Autonomous Self-Maintenance (Lint & Auto-Heal)**, an **Interactive Force-Directed Knowledge Graph**, **Token/Cost Telemetry**, and **Grounded Multi-Turn Wiki Chat** with **File-to-Wiki** compounding synthesis.

## Architecture (3 Layers)

1. **`vault/raw/` (Immutable Raw Sources)** — Original articles, papers, and clippings. Never modified by the LLM.
2. **`vault/wiki/` (LLM-Owned Compiled Wiki)** — Interlinked Markdown pages with YAML frontmatter and `[[wikilinks]]` organized into `concepts/`, `entities/`, `sources/`, and `syntheses/`, plus `vault/index.md`, `vault/log.md`, and `vault/.history/` revision diffs.
3. **`vault/SCHEMA.md` (The Schema)** — Rules and workflows governing ingestion, similarity-first updating, cross-referencing, contradictions tracking, and self-maintenance.

---

## Quick Start

```bash
# 1. Activate the virtual environment
source .venv/bin/activate

# 2. Run the FastAPI server
uvicorn backend.app:app --host 127.0.0.1 --port 8000

# 3. Open in your browser:
#    - Main App: http://127.0.0.1:8000
#    - Architecture Guide: http://127.0.0.1:8000/guide
```

---

## Configuring LLM Providers & API Tokens

Out of the box, the system runs in **`local_smart`** mode (deterministic offline synthesis + TF-IDF/BM25/Graph similarity) so ingestion, deduplication, self-maintenance, and chat work with zero API keys.

To enable a live LLM for synthesis and grounded QA, configure credentials via **Environment Variables**, the **Web UI Settings modal**, or **`POST /api/settings`**.

### Option 1: Environment Variables (before starting `uvicorn`)

```bash
# Google Gemini (default model: gemini-3.5-flash-lite)
export GEMINI_API_KEY="your-gemini-api-key"
export GEMINI_MODEL="gemini-3.5-flash-lite"

# OR OpenAI / OpenAI-Compatible Endpoint
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-4o-mini"

# OR Internal OpenAI-Compatible Gateway using Custom Headers (no API key needed)
export LLM_WIKI_PROVIDER="openai"
export OPENAI_BASE_URL="https://your-gateway.internal/v1"
export OPENAI_MODEL="your-model"
export OPENAI_CUSTOM_HEADERS='{"sid": "your-sid", "env": "prod", "x-special-no": "12345"}'

# OR Ollama Local LLM
export LLM_WIKI_PROVIDER="ollama"
export OLLAMA_BASE_URL="http://127.0.0.1:11434"
export OLLAMA_MODEL="llama3.2"
```

### Option 2: Runtime via `POST /api/settings` (or Settings Modal in UI)

```bash
curl -X POST http://127.0.0.1:8000/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "gemini",
    "gemini_api_key": "your-gemini-api-key",
    "gemini_model": "gemini-3.5-flash-lite"
  }'
```

For an OpenAI-compatible gateway with custom headers (`sid`, `env`, etc.):

```bash
curl -X POST http://127.0.0.1:8000/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openai",
    "openai_api_key": "",
    "openai_base_url": "https://your-gateway.internal/v1",
    "openai_model": "your-model",
    "openai_custom_headers": {
      "sid": "your-sid",
      "env": "prod",
      "x-special-no": "12345"
    }
  }'
```

---

## How to Use via REST API

### 1. Ingest Knowledge (`POST /api/ingest/execute`)

`POST /api/ingest/execute` checks similarity against existing wiki pages first: if a matching page exists above `similarity_threshold`, it **updates/merges** into that page; otherwise it **creates** a new page.

```bash
curl -X POST http://127.0.0.1:8000/api/ingest/execute \
  -H "Content-Type: application/json" \
  -d '{
    "title": "LTE UE Category 10",
    "content": "UE Category 10 supports peak downlink throughput around 450 Mbps using carrier aggregation.",
    "source_name": "3gpp-notes.txt"
  }'
```

*(Optional)* Preview whether an input will `update` or `create` without modifying the vault using `POST /api/ingest/preview` with `{"title": "...", "content": "..."}`.

### 2. Ask Questions (`POST /api/chat`)

Send a question (and optional multi-turn `history`) to retrieve the top matching wiki pages and generate a grounded answer:

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the peak downlink throughput of LTE UE Category 10?",
    "history": []
  }'
```

Python example:

```python
import httpx

resp = httpx.post(
    "http://127.0.0.1:8000/api/chat",
    json={
        "question": "What is the peak downlink throughput of LTE UE Category 10?",
        "history": [
            {"role": "user", "content": "Tell me about LTE categories."},
            {"role": "assistant", "content": "LTE UE Categories define throughput capabilities..."},
        ],
    },
    timeout=60.0,
)
data = resp.json()

print("Answer:\n", data["answer"])
print("\nCitations:")
for c in data["cited_pages"]:
    print(f" - [{c['category']}] {c['title']} (slug={c['slug']}, score={c['score']})")
```

### 3. What `/api/chat` Returns & How to Get Citations

`/api/chat` returns a JSON object with this structure:

```json
{
  "answer": "LTE UE Category 10 supports peak downlink throughput around 450 Mbps using carrier aggregation ([[lte-ue-category-10]]).",
  "cited_pages": [
    {
      "slug": "lte-ue-category-10",
      "title": "LTE UE Category 10",
      "category": "concepts",
      "score": 0.8421
    }
  ],
  "provider_mode": "gemini",
  "model_name": "gemini-3.5-flash-lite",
  "telemetry": {
    "llm_used": true,
    "llm_calls": 1,
    "local_operations": 1,
    "input_tokens": 1120,
    "output_tokens": 64,
    "total_tokens": 1184,
    "cost_usd": 0.000138,
    "models": ["gemini-3.5-flash-lite"]
  }
}
```

How to read citations:
- **Structured citations:** Read `data["cited_pages"]` — each item gives `slug`, `title`, `category`, and retrieval `score`.
- **Fetch full cited page content:** Call `GET /api/pages/{slug}` (e.g., `GET /api/pages/lte-ue-category-10`) to get the full Markdown body, YAML metadata, `backlinks`, `outbound_links`, and revision `history`.
- **Inline citations:** The `answer` text also includes Markdown `[[slug]]` wikilinks referencing the consulted pages.

### 4. Other Useful Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/pages` | `GET` | List all wiki pages |
| `/api/pages/{slug}` | `GET` | Read full page content, links, and diff history |
| `/api/search` | `POST` | Hybrid BM25 + TF-IDF + graph search (`{"query": "...", "top_k": 5}`) |
| `/api/graph` | `GET` | Knowledge graph nodes and edges (`wikilink` + `semantic`) |
| `/api/chat/file-to-wiki` | `POST` | Save a synthesized chat answer back into the wiki |
| `/api/lint` / `/api/lint/heal` | `GET` / `POST` | Audit and auto-heal orphans, dangling links, and near-duplicates |
| `/api/telemetry` | `GET` | Token usage, USD cost, latency, and dedup savings log |
| `/docs` | `GET` | Interactive FastAPI Swagger UI for all endpoints |

---

## Running Tests

```bash
.venv/bin/pytest tests/test_wiki_system.py -v
```
