# 100-Passage (4x Redundant) Knowledge Base & QA Benchmark Report

Dataset: **SQuAD v1.1 Dev (25 topics x 4 redundant passages = 100 passages, 50 QA pairs)**

## 1. Similarity-First Ingest & Intra-Page Redundancy Deduplication (100 Passages)

- **Elapsed Time (100 Ingests + Auto-Maintain)**: `47.635s`
- **Final Vault Size**: `34` wiki pages (`9` starter + `25` canonical SQuAD pages; `75` duplicate pages prevented), `103` immutable raw sources
- **Health Score / Near-Duplicates Remaining**: `100%` health score, `0` near-duplicate pairs

| Wave (25 Passages Each) | Role / Redundancy Type | Created | Updated In-Place | Canonical Match Rate | Novel Blocks Added | Redundant Blocks Skipped | Body Growth (chars) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Wave 1 (Canonical Seed)** | wave_1 | 25 | 0 | 25/25 (100.0%) | 0 | 0 | 0 |
| **Wave 2 (Varied-Title Exact Copy)** | wave_2 | 0 | 25 | 25/25 (100.0%) | 0 | 25 | 0 |
| **Wave 3 (Reordered P1 + Novel P2)** | wave_3 | 0 | 25 | 25/25 (100.0%) | 25 | 25 | 25888 |
| **Wave 4 (Noisy/Blind-Title Excerpt)** | wave_4 | 0 | 25 | 25/25 (100.0%) | 0 | 25 | 0 |

## 2. Retrieval & QA Correctness After 100-Passage 4x Redundant Ingest (50 SQuAD QAs)

- **Evaluation Runtime (50 Searches + 50 Chat QAs)**: `4.481s`

| Metric | Overall (50 QAs) | P1 Initial (25 QAs) | P2 Wave-3 Novel (25 QAs) |
| :--- | :---: | :---: | :---: |
| **Retrieval Recall@1** | 98.0% | 100.0% | 96.0% |
| **Retrieval Recall@3** | 100.0% | 100.0% | 100.0% |
| **Mean Reciprocal Rank (MRR)** | 0.990 | 1.000 | 0.980 |
| **Citation Accuracy** | 100.0% | 100.0% | 100.0% |
| **Gold Span Match (Full Chat Answer)** | 98.0% | 100.0% | 96.0% |
| **Gold Span Match (Direct Answer)** | 90.0% | 96.0% | 84.0% |
| **Direct Answer Token Recall** | 90.7% | 97.3% | 84.0% |

## 3. Forced 4x Redundant Proliferation -> Self-Maintaining Linter Auto-Merge

- **Before Heal (`force_create=True` × 100)**: `109` pages, `132` detected near-duplicate pairs, Health Score `10%`
- **Auto-Merge Executed (`POST /api/lint/heal`)**: `75` redundant pages auto-merged & deleted in `17.949s`
- **After Heal**: `34` pages (`9` starter + `25` canonical), `0` near-duplicates remaining, `0` dangling links, Health Score `100%`
- **Inbound Clone Wikilinks Redirected Cleanly**: `PASS`
- **Post-Heal 50-QA Full-Span Accuracy (Zero Knowledge Loss)**: `49/50` (**98.0%**)
