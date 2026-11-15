# Simple E5 Dense Vector RAG vs. LLM Wiki Head-to-Head Benchmark

- **Dense Embedding Baseline**: `intfloat/multilingual-e5-large` on `cuda (NVIDIA GeForce RTX 3060 Laptop GPU)` (passage-level + <=1000-char sentence-chunked variants)
- **Dataset**: Ericsson TeleQuAD v4 (`20` topics × `10x` redundant waves = `200` passages, `100` questions) + `5` 3GPP Release-18 Specification Revisions
- **Generator for Live Reader Comparison**: `gemini-3.5-flash-lite` (`store=False`, identical system prompt across both retrievers)

## 1. Indexing Speed & Vault Footprint (200 Redundant Passages)

| System | Indexed Units | Indexing / Ingest Time | Redundant Duplicate Units Stored |
| :--- | :---: | :---: | :---: |
| **E5 Dense RAG (Whole-Passage, GPU)** | `200` vectors | `11.709s` (+ `5.427s` model load) | `180` duplicate passages (90%) |
| **E5 Dense RAG (Sub-Chunked <=1000c, GPU)** | `415` vectors | `13.683s` | `90%` redundant sub-chunks |
| **LLM Wiki (Compiled Graph Vault)** | `20` TeleQuAD pages (`29` total) | `51.665s` (dedup + wikilinks + lint) | **`0` duplicates (`100%` merged)** |

## 2. 100-Question TeleQuAD Retrieval & Extractive Precision / Recall / F1

| Metric | E5 RAG (Whole Passage) | E5 RAG (Sub-Chunked) | LLM Wiki |
| :--- | :---: | :---: | :---: |
| **Topic Recall@1** | 96.0% | 97.0% | **99.0%** |
| **Topic Recall@3** | 98.0% | 98.0% | **100.0%** |
| **Gold Answer Present in Top-1 Unit** | 86.0% | 91.0% | **99.0%** |
| **Gold Answer Present in Top-3 Units** | 96.0% | 93.0% | **100.0%** |
| **Part-B Gold Present in Top-1 (38 QAs)** | 81.6% | 84.2% | **100.0%** |
| **Part-B Gold Present in Top-3 (38 QAs)** | 92.1% | 86.8% | **100.0%** |
| **Top-3 Wasted Redundant Slots (%)** | 35.3% | 38.0% | **0.0%** |
| **Top-1 Sentence Span Match (Equal Budget)** | 70.0% | 77.0% | **84.0%** |
| **Top-1 Sentence Token Recall / F1** | 73.5% / 36.6% | 79.3% / 40.1% | **85.9% / 41.0%** |
| **Direct / Top-1 Chunk Recall / F1** | 88.9% / 13.7% | 92.9% / 20.6% | **96.4% / 20.8%** |
| **Full-Context Answer Gold Span Match** | 96.0% *(Top-3 raw)* | 93.0% *(Top-3 raw)* | **100.0%** |

## 3. Stale-History Crowding Test (10 Stale Waves + 1 Spec Revision per Topic)

Natural domain questions ask about the updated rule without mentioning secret revision IDs:

| Metric (5 Spec Revisions) | E5 RAG (Whole Passage) | E5 RAG (Sub-Chunked) | LLM Wiki (Compiled In-Place) |
| :--- | :---: | :---: | :---: |
| **Revision Present in Top-1 Context** | 100.0% | 100.0% | **100.0%** |
| **Revision Present in Top-3 Context** | 100.0% | 100.0% | **100.0%** *(Top-1 alone)* |

## 4. Same-Generator Head-to-Head (`gemini-3.5-flash-lite`, 10 Live Queries)

Identical `gemini-3.5-flash-lite` prompt reading **E5 Sub-Chunked Top-3** vs. **LLM Wiki Top-1 Canonical Page**:

| Subset | E5 Top-3 + Gemini Accuracy | LLM Wiki Top-1 + Gemini Accuracy | E5 Avg Term Recall | Wiki Avg Term Recall |
| :--- | :---: | :---: | :---: | :---: |
| **Overall (10 Queries)** | 90.0% | **90.0%** | 100.0% | **96.7%** |
| **TeleQuAD Part-B (5 QAs)** | 80.0% | **100.0%** | 100.0% | **100.0%** |
| **3GPP Spec Revisions (5 QAs)** | 100.0% | **80.0%** | 100.0% | **93.3%** |
