# TeleQuAD 200-Passage (10x Redundant) & 100-Question Benchmark Report

Dataset: **Ericsson Research TeleQuAD v4 (20 telecom/3GPP topics x 10 waves = 200 passages, 100 QA pairs)**

## 1. Similarity-First Ingest & Intra-Page 10x Redundancy Deduplication (200 Passages)

- **Elapsed Time (200 Ingests + Auto-Maintain)**: `77.117s`
- **Final Vault Size**: `29` wiki pages (`9` starter + `20` canonical TeleQuAD pages; `180` duplicate pages prevented), `203` immutable raw sources
- **Health Score / Near-Duplicates Remaining**: `100%` health score, `0` near-duplicate pairs

| Wave (20 Passages Each) | Role / Redundancy Pattern | Created | Updated In-Place | Canonical Match Rate | Novel Blocks Added | Redundant Skipped | Body Growth (chars) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Wave 1: Canonical Seed (Part A)** | `canonical_create` | 20 | 0 | 20/20 (100.0%) | 0 | 0 | 0 |
| **Wave 2: Varied Title Copy (Part A)** | `exact_copy_varied_title` | 0 | 20 | 20/20 (100.0%) | 0 | 20 | 0 |
| **Wave 3: Reordered Sentences (Part A)** | `reordered_part_a` | 0 | 20 | 20/20 (100.0%) | 0 | 20 | 0 |
| **Wave 4: Hybrid (Part A + Novel Part B)** | `hybrid_part_a_plus_novel_part_b` | 0 | 20 | 20/20 (100.0%) | 20 | 28 | 30936 |
| **Wave 5: Varied Title Copy (Part B)** | `exact_copy_part_b` | 0 | 20 | 20/20 (100.0%) | 0 | 20 | 0 |
| **Wave 6: Reordered Sentences (Part B)** | `reordered_part_b` | 0 | 20 | 20/20 (100.0%) | 0 | 20 | 0 |
| **Wave 7: Cross-Section Excerpt (A + B)** | `cross_section_excerpt` | 0 | 20 | 20/20 (100.0%) | 0 | 40 | 0 |
| **Wave 8: Blind Title Memo (Part A)** | `blind_title_part_a` | 0 | 20 | 20/20 (100.0%) | 0 | 20 | 0 |
| **Wave 9: Blind Title Audit Log (Part B)** | `blind_title_part_b` | 0 | 20 | 20/20 (100.0%) | 0 | 20 | 0 |
| **Wave 10: Consolidated Reordered Mirror** | `consolidated_reordered_mirror` | 0 | 20 | 20/20 (100.0%) | 0 | 40 | 0 |

## 2. Retrieval & QA Correctness After 200-Passage 10x Redundant Ingest (100 TeleQuAD QAs)

- **Evaluation Runtime (100 Searches + 100 Chat QAs)**: `8.965s`

| Metric | Overall (100 QAs) | Part A Initial (62 QAs) | Part B Wave-4 Novel (38 QAs) |
| :--- | :---: | :---: | :---: |
| **Retrieval Recall@1** | 99.0% | 98.4% | 100.0% |
| **Retrieval Recall@3** | 100.0% | 100.0% | 100.0% |
| **Mean Reciprocal Rank (MRR)** | 0.995 | 0.992 | 1.000 |
| **Citation Accuracy** | 100.0% | 100.0% | 100.0% |
| **Gold Span Match (Full Chat Answer)** | 100.0% | 100.0% | 100.0% |
| **Gold Span Match (Direct Answer)** | 96.0% | 93.5% | 100.0% |
| **Direct Answer Token Recall** | 96.4% | 94.4% | 99.6% |

## 3. Forced 10x Redundant Proliferation -> Self-Maintaining Linter Auto-Merge

- **Before Heal (`force_create=True` × 200)**: `209` pages, `597` detected near-duplicate pairs, Health Score `10%`
- **Auto-Merge Executed (`POST /api/lint/heal`)**: `180` redundant clone pages auto-merged & deleted in `47.339s`
- **After Heal**: `29` pages (`9` starter + `20` canonical), `0` near-duplicates remaining, `0` dangling links, Health Score `100%`
- **Inbound Clone Wikilinks Redirected Cleanly**: `PASS`
- **Post-Heal 100-QA Full-Span Accuracy (Zero Knowledge Loss)**: `100/100` (**100.0%**)
