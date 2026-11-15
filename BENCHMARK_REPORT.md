# Public QA & Fake-Data Update Benchmark Report

Dataset: **SQuAD v1.1 Dev** (6 articles × 3 paragraphs = 18 passages, 36 QA pairs) + **4 Fake/Counterfactual Update Sources** (8 QA pairs).

## 1. Multi-Passage Ingest & Update-Instead-of-Create

- **Wave 1 Pages Created**: `6 / 6`
- **Wave 2 & 3 Updates Merged In-Place (No Duplicates)**: `12 / 12` (**100.0%**)
- **Final Vault State**: `15` wiki pages, `25` immutable raw sources, Health Score `100%`

## 2. Public QA Retrieval & Answer Correctness (36 SQuAD Questions)

| Metric | Overall (36 QAs) | Wave 1 (Initial, 12 QAs) | Wave 2 (Update r2, 12 QAs) | Wave 3 (Update r3, 12 QAs) |
| :--- | :---: | :---: | :---: | :---: |
| **Retrieval Recall@1** | 100.0% | 100.0% | 100.0% | 100.0% |
| **Retrieval Recall@3** | 100.0% | 100.0% | 100.0% | 100.0% |
| **Mean Reciprocal Rank (MRR)** | 1.000 | 1.000 | 1.000 | 1.000 |
| **Citation Accuracy** | 100.0% | 100.0% | 100.0% | 100.0% |
| **Gold Span Match (Full Chat Answer)** | 94.4% | 100.0% | 100.0% | 83.3% |
| **Gold Span Match (Direct Answer)** | 88.9% | 83.3% | 100.0% | 83.3% |
| **Direct Answer Token Recall** | 88.9% | 87.5% | 91.7% | 87.5% |

## 3. Fake / Counterfactual Data Update Verification (4 Synthetic Sources, 8 QAs)

- **Pre-Update Fake QA Hits**: `0 / 8`
- **In-Place Updates Executed**: `4 / 4` (zero duplicate pages created)
- **Post-Update Fake QA Hits**: `8 / 8` (**100.0%**)
- **Original SQuAD Retention After Fake Updates**: **94.4%**

| Target Page | Rev Before → After | Contradictions Section | Fake QA Passed |
| :--- | :---: | :---: | :---: |
| `[[nikola-tesla]]` | r4 → r5 | Yes | PASS |
| `[[computational-complexity-theory]]` | r3 → r4 | Yes | PASS |
| `[[super-bowl-50]]` | r3 → r4 | Yes | PASS |
| `[[llm-wiki-pattern]]` | r2 → r3 | Yes | PASS |

---

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

---

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

---

# Live Gemini Free-Tier Benchmark Report

Provider Mode: **`gemini`** (`gemini-3.5-flash-lite` via Google Gemini Interactions API)

## 1. Gemini Model Latency & Structured JSON Comparison

| Model | Status | Latency (s) | Valid JSON Schema | Extracted 3GPP SCS (kHz) |
| :--- | :---: | :---: | :---: | :--- |
| `gemini-3.5-flash-lite` | OK | 1.407s | PASS | 15, 30, 60, 120, 240 |
| `gemini-3.1-flash-lite` | OK | 8.091s | PASS | 15, 30, 60, 120, 240 |
| `gemini-4-hydrogen` | OK | 46.549s | PASS | 15, 30, 60, 120, 240 |

## 2. Similarity-First Multi-Wave Ingest & Live Gemini Synthesis (20 Passages)

- **Elapsed Time (20 Ingests + Auto-Maintain + 5 Live Gemini Syntheses)**: `11.342s`
- **Final Vault State**: `14` wiki pages (`9` starter + `5` canonical TeleQuAD), `23` raw sources, Health Score `100%`, `0` near-duplicates

| Wave (5 Passages Each) | Wave Type | Created | Updated | Canonical Match | Novel Added | Redundant Skipped | Body Growth (chars) | Live Gemini Calls |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Wave 1** | `canonical_create` | 5 | 0 | 5/5 | 0 | 0 | 0 | 0 |
| **Wave 2** | `exact_copy_varied_title` | 0 | 5 | 5/5 | 0 | 5 | 0 | 0 |
| **Wave 3** | `reordered_part_a` | 0 | 5 | 5/5 | 0 | 5 | 0 | 0 |
| **Wave 4** | `hybrid_part_b_plus_counterfactual` | 0 | 5 | 5/5 | 5 | 6 | 6604 | 5 |

### Wave 4 Live Gemini Update Synthesis Samples

| Target Page | Rev | Contradictions Tracked | Gemini-Synthesized Change Note |
| :--- | :---: | :---: | :--- |
| `[[3gpp-23273-g50-support-of-concurrent-location-requests]]` | r4 → r5 | No | Integrated extended procedures for request combining across V-GMLC, AMF, LMF, and UE along with H-GMLC bulk request conditions under clauses |
| `[[3gpp-23009-g00-enhanced-srns-relocation]]` | r4 → r5 | No | Integrated post-response procedures including IU-ENHANCED-RELOCATION-COMPLETE messages, Iu UP initialization, and the final IURELEASECOMMAND |
| `[[3gpp-21915-f00-numerologies-waveform-and-frame-structure]]` | r3 → r4 | No | Integrated new details covering slot symbol structures, extended CP for 60 kHz SCS, FDD/TDD symbol classification, and ultra-short transmiss |
| `[[3gpp-32240-f50-charging-levels-and-correlation]]` | r4 → r5 | Yes | Integrated the 2026 Release-99 Chronos Audit Override specifying CHRONOS-BILLING-X9 quantum receipts, a 3 transit IOI cap, and the X-3GPP-AU |
| `[[uniform-resource-identifier-uri-list]]` | r3 → r4 | Yes | Replaced the legacy email application process to the TSG CT WG1 Secretary with portal URN-GATEWAY-77B and cipher tag NID-QUANTUM-55 per TSG- |

## 3. Live Gemini Grounded Chat QA (6 TeleQuAD + 2 Counterfactual Override QAs)

- **Chat Evaluation Runtime (8 Live Queries)**: `9.525s` (avg `1.166s/query`)
- **Gemini Telemetry (`llm_stats`)**: `13/13` succeeded, `0` failed, `16.8338s` cumulative Gemini API time

| Metric | Overall (8 QAs) | TeleQuAD (6 QAs) | Counterfactual R99 (2 QAs) |
| :--- | :---: | :---: | :---: |
| **Retrieval Recall@1** | 100.0% | 100.0% | 100.0% |
| **Retrieval Recall@3** | 100.0% | 100.0% | 100.0% |
| **Citation Accuracy** | 100.0% | 100.0% | 100.0% |
| **Pure Gemini Prose Match** | 75.0% | 66.7% | 100.0% |
| **Pure Gemini Token Recall** | 100.0% | 100.0% | 100.0% |
| **Wiki Hybrid Direct Span Match** | 100.0% | 100.0% | 100.0% |
| **Gold Span Match (Full Chat Answer)** | 100.0% | 100.0% | 100.0% |

---

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

---

# Full Ericsson TeleQuAD Benchmark Report (536 Passages, 4,485 Questions)

## Benchmark Configuration & Dataset Profile
- **Dataset**: Full [TeleQuAD-v4-full.json](file:///home/darwin/llm-wiki/tests/fixtures/TeleQuAD-v4-full.json) — **`536` passages**, **`4,485` extractive QA pairs**, across **`96` 3GPP specs / telecom article groups** (`16` multi-clause 3GPP specs with `2`–`79` sibling passages per spec; `80` standalone telecom articles).
- **Passage Length Distribution**: min `202` chars, median `1,211` chars, avg `2,093.5` chars, max `36,373` chars (`360` passages <= 2,000 chars covering `2,024` QAs; `176` long passages > 2,000 chars covering `2,461` QAs).
- **Dense Embedding Baseline**: `intfloat/multilingual-e5-large` on `cuda (NVIDIA GeForce RTX 3060 Laptop GPU)` (`9.088s` model load time excluded from index build timings).

## 1. Overall Retrieval Accuracy Across All 4,485 Questions

| Architecture | Indexed Units | Passage R@1 | Passage R@3 | Passage R@5 | Passage R@10 | Passage MRR@10 | Spec R@1 | Spec R@3 | Spec R@5 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. E5-Large Whole-Passage RAG (512-tok cap)** | `536` | 50.06% | 65.69% | 71.22% | 78.08% | `0.5925` | 75.76% | 84.68% | 88.03% |
| **2. E5-Large Sub-Chunked RAG (<=1000c MaxP)** | `1,553` | 63.52% | 79.18% | 83.50% | 88.94% | `0.7217` | 84.86% | 92.46% | 94.76% |
| **3. LLM Wiki HybridSimilarityEngine (536 Passage Pages)** | `536` | 75.96% | 89.19% | 93.15% | 95.88% | `0.8318` | 90.23% | 95.88% | 97.32% |
| **4. Hybrid LLM Wiki + E5 Sub-Chunked Fusion (Norm Score + RRF)** | `536` | 77.39% | 90.79% | 93.98% | 96.63% | `0.8450` | 91.95% | 96.88% | 97.95% |
| **5. LLM Wiki Spec-Consolidated Granularity (96 Spec Pages)** | `96` | N/A *(96 specs)* | N/A *(96 specs)* | N/A *(96 specs)* | N/A *(96 specs)* | N/A | 87.22% | 96.32% | 97.68% |

*Hybrid Fusion Ablation (`4,485` QAs)*: Norm-Only Score Fusion (`0.62*Wiki + 0.38*E5`) achieved **Passage R@1 = 77.61%**, R@3 = 90.70%, R@10 = 96.74%, MRR = `0.8463`; Pure RRF (`k=60`) achieved **Passage R@1 = 71.93%**, R@3 = 86.85%, R@10 = 94.94%, MRR = `0.8007`.

## 2. Gold Answer Containment & Extractive Top-1 Sentence QA Accuracy

| Architecture | Ans-in-Top-1 | Ans-in-Top-3 | Ans-in-Top-5 | Ans-in-Top-10 | Top-1 Sent Span Match | Top-1 Sent >= 0.5 Recall | Top-1 Sent Recall | Top-1 Sent F1 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. E5-Large Whole-Passage RAG (512-tok cap)** | 56.03% | 70.93% | 75.92% | 81.87% | 40.85% | 45.86% | 48.36% | 24.00% |
| **2. E5-Large Sub-Chunked RAG (<=1000c MaxP)** | 62.34% | 75.50% | 79.13% | 82.81% | 49.10% | 55.23% | 57.44% | 27.26% |
| **3. LLM Wiki HybridSimilarityEngine (536 Passage Pages)** | 80.91% | 91.91% | 95.03% | 96.88% | 61.83% | 66.71% | 67.81% | 32.59% |
| **4. Hybrid LLM Wiki + E5 Sub-Chunked Fusion (Norm Score + RRF)** | 83.17% | 93.76% | 95.90% | 97.68% | 62.81% | 67.47% | 68.87% | 32.89% |
| **5. LLM Wiki Spec-Consolidated Granularity (96 Spec Pages)** | 88.70% | 96.68% | 97.86% | 98.73% | 61.27% | 66.22% | 67.47% | 31.84% |

*Note*: For Sub-Chunked E5 (`<=1,000`-char MaxP chunks), `Ans-in-Top-K` and `Top-1 Sent` evaluate the winning `<=1,000`-char chunks (which improves sentence isolation inside long docs when the right chunk lands at rank 1); for Arch 5 (Spec-Consolidated `96` pages), each page aggregates all clauses of a spec so `Ans-in-Top-K` tracks spec coverage while `Top-1 Sent` shows whether the extractive sentence matcher locates the exact sentence inside a full 3GPP spec body.

## 3. Stratified Performance: Passage Length & Multi-Clause Spec Ambiguity

| Architecture | Short (`<=2k`c, `2,024` QAs) R@1 / Ans@1 | Long (`>2k`c, `2,461` QAs) R@1 / Ans@1 | Multi-Clause Specs (`3,638` QAs) R@1 / R@10 | Standalone Articles (`847` QAs) R@1 / R@10 |
| :--- | :---: | :---: | :---: | :---: |
| **1. E5-Large Whole-Passage RAG (512-tok cap)** | 64.18% / 69.27% | 38.44% / 45.14% | 50.33% / 80.26% | 48.88% / 68.71% |
| **2. E5-Large Sub-Chunked RAG (<=1000c MaxP)** | 64.23% / 66.21% | 62.94% / 59.16% | 61.27% / 88.35% | 73.20% / 91.50% |
| **3. LLM Wiki HybridSimilarityEngine (536 Passage Pages)** | 78.75% / 83.20% | 73.67% / 79.03% | 75.12% / 95.79% | 79.57% / 96.22% |
| **4. Hybrid LLM Wiki + E5 Sub-Chunked Fusion (Norm Score + RRF)** | 79.20% / 84.29% | 75.90% / 82.24% | 75.84% / 96.34% | 84.06% / 97.87% |
| **5. LLM Wiki Spec-Consolidated Granularity (96 Spec Pages)** | Spec 87.60% / 89.23% | Spec 86.92% / 88.26% | Spec 87.71% / 97.77% | Spec 85.12% / 97.28% |

## 4. Indexing & Query Latency (All 4,485 Queries)

| Architecture | Build / Embed Time | Total 4,485-Query Time | Per-Query Latency |
| :--- | :---: | :---: | :---: |
| **1. E5-Large Whole-Passage RAG (512-tok cap)** | `40.243s` | `18.572s` | `4.141 ms/query` |
| **2. E5-Large Sub-Chunked RAG (<=1000c MaxP)** | `113.735s` | `18.673s` | `4.163 ms/query` |
| **3. LLM Wiki HybridSimilarityEngine (536 Passage Pages)** | `0.769s` | `56.350s` | `12.564 ms/query` |
| **4. Hybrid LLM Wiki + E5 Sub-Chunked Fusion (Norm Score + RRF)** | `114.504s` | `75.351s` | `16.801 ms/query` |
| **5. LLM Wiki Spec-Consolidated Granularity (96 Spec Pages)** | `2.162s` | `16.691s` | `3.722 ms/query` |

## 5. Key Honest Takeaways
1. **Whole-Passage Dense Vector RAG Breaks on Long Technical Clauses**: Single-vector `intfloat/multilingual-e5-large` truncates beyond 512 tokens and scores only **50.06% Passage R@1** (**38.44%** on >2,000-char clauses). Sub-chunking into `<=1,000`-char overlapping windows with MaxP lifts E5 dramatically to **63.52% Passage R@1** (`+13.46 pp`), especially on long clauses (**62.94%**).
2. **LLM Wiki `HybridSimilarityEngine` Beats Even Sub-Chunked GPU E5 on Fine-Grained 3GPP Clause Retrieval**: On pure CPU in **`56.35s` total (`12.564 ms/query`)**, `HybridSimilarityEngine` reaches **75.96% Passage R@1**, **93.15% R@5**, and **95.88% R@10** (`MRR 0.8318`), vs. Sub-Chunked E5's 63.52% R@1 / 88.94% R@10. Why? 3GPP questions rely on exact identifiers, section numbers, parameter acronyms, and bigrams (`Layer 2`, `SCS`, numeric caps, IE names) across 39–79 nearly identical sibling clauses inside the same specification—where IDF-weighted lexical + bigram BM25 outperforms bi-encoder semantic pooling.
3. **Hybrid Fusion Achieves the Best Overall Accuracy**: Combining `HybridSimilarityEngine` with Sub-Chunked `E5-large` pushes **Passage R@1 to 77.39%**, **R@3 to 90.79%**, **R@10 to 96.63%**, and **`MRR` to `0.8450`**—simultaneously excelling on exact 3GPP terminology AND paraphrased natural-language queries.
4. **Spec-Consolidated Pages Need Section-Level Sub-Indexing for Multi-Clause Specs**: Consolidating 536 passages into 96 Spec pages yields **87.22% Spec R@1** (**88.70%** gold presence in Top-1 page), while keeping per-clause granularity (`536` pages/sections) yields higher pinpoint sentence accuracy (**61.83%** vs. **61.27%** Top-1 sentence span match) because searching across ~1,000 sentences inside an entire 79-clause spec adds distractor overlap.

---

---

---

# Full TeleQuAD 10x Redundancy Benchmark Report (5,360 Full Passages, 4,485 Questions)

## Benchmark Configuration & Zero-Shortcut Blind Consolidation Summary
- **Dataset**: Full [TeleQuAD-v4-full.json](file:///home/darwin/llm-wiki/tests/fixtures/TeleQuAD-v4-full.json) expanded across **`10` full-passage waves** (`536` canonical passages × `10` = **`5,360` full passages**, **`11,256,986` chars**) and evaluated on all **`4,485` extractive QA pairs** (`2,024` QAs on standard passages `<=2,000` chars; `2,461` QAs on long passages `>2,000` chars / `>512` E5 tokens).
- **Zero Benchmark Shortcuts (100% Blind Ingestion)**:
  1. **No passage slicing**: Every wave contains the full passage (not chopped into shorter `part_a`/`part_b` halves that would artificially cure E5's 512-token truncation).
  2. **No Wave-1 bypass**: Ingestion starts from an empty vault (`pages = {}`) at Document #1 of Wave 1 and calls `find_similar_for_candidate(..., threshold=0.35)` on all `5,360` documents.
  3. **No ground-truth tags**: Tags are extracted purely from document text via `LLMService._extract_tags`.
  4. **Live incremental indexing**: `HybridSimilarityEngine.upsert_page` indexes each created/updated page immediately without any post-hoc extra-page cleanup pass.
- **LLM Wiki Blind Consolidation Result**: `5,360` incoming passages compiled down to **`548` canonical pages** in **`19.08s`** (`4` Wave-1 near-duplicate pairs consolidated during Wave 1: two word-for-word identical 3GPP RAN2/RAN5 web scrapes `#97==#209` and `#100==#417`, plus two 94%-identical TS 23.009 handover clauses `#75==#491` and `#233==#276`; **`4,808/4,824` (99.67%)** of Wave 2–10 items consolidated via in-place updates; **`25,044` redundant blocks/sentences skipped**; stored corpus text compressed by **`87.2%`** from `11,256,986` chars to `1,439,603` chars).

## 1. Per-Wave Blind LLM Wiki Consolidation (Waves 1–10 × 536 Full Passages)

| Wave | Wave Type | Incoming | Created | Updated | Target Page Match | Novel Blocks Kept | Redundant Skipped |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `Wave 1` | `Canonical Full Passage` | `536` | `532` | `4` | `536/536` (`100.00%`) | `536` | `13` |
| `Wave 2` | `Technical Note Duplicate` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `4,677` |
| `Wave 3` | `Spec Digest (Local Sent Swap)` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `536` |
| `Wave 4` | `Extended Header Duplicate` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `4,677` |
| `Wave 5` | `Addendum Notes Duplicate` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `4,677` |
| `Wave 6` | `Protocol Summary (Sent Swap)` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `536` |
| `Wave 7` | `Telecom Reference Sheet` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `536` |
| `Wave 8` | `Blind Archive Memo (#08-XXX)` | `536` | `8` | `528` | `528/536` (`98.51%`) | `8` | `4,187` |
| `Wave 9` | `Blind Field Audit Log (#09-XXX)` | `536` | `8` | `528` | `527/536` (`98.32%`) | `8` | `528` |
| `Wave 10` | `Consolidated Spec Mirror` | `536` | `0` | `536` | `536/536` (`100.00%`) | `0` | `4,677` |

## 2. 1x Baseline vs. 10x Redundancy Retrieval & Crowding Across All 4,485 Questions

| System | Indexed Units | Dup Rate | Topic R@1 (Strict 1-to-1) | Topic R@3 | Topic R@5 | Topic R@10 (Strict 1-to-1) | Top-3 Wasted Slots | Top-10 Wasted Slots | Unique Topics in Top-10 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Ref: E5 Whole-Passage (1x Non-Redundant)** | `536` | `0.0%` | `50.06%` | `65.69%` | `71.22%` | `78.08%` | `0.00%` | `0.00%` | `10.00 / 10` |
| **Ref: E5 Sub-Chunked (1x Non-Redundant)** | `1,553` | `0.0%` | `63.52%` | `79.18%` | `83.50%` | `88.94%` | `0.00%` | `0.00%` | `10.00 / 10` |
| **1. E5-Large Whole-Passage RAG (5,360 Raw Wave Docs)** | `5,360` | `90.0%` | 52.91% | 56.79% | 59.09% | 64.24% | 57.56% | 79.86% | `2.01 / 10` |
| **2. E5-Large Sub-Chunked (<=1000c, Wave-Doc MaxP, 15,687 chunks)** | `15,687` | `96.6%` | 67.07% | 72.24% | 74.31% | 79.00% | 58.32% | 80.63% | `1.94 / 10` |
| **3. LLM Wiki Consolidated Vault (548 Pages)** | `548` | `2.9%` | 76.12% (`75.94%`) | 89.07% | 93.15% | 95.85% (`95.63%`) | 3.27% | 4.16% | `9.56 / 10` |
| **4. Hybrid LLM Wiki + E5 Fusion (548 Consolidated Pages)** | `548` | `2.9%` | 77.64% (`77.48%`) | 90.39% | 93.78% | 96.72% (`96.50%`) | 3.83% | 5.22% | `9.48 / 10` |

*Sub-Chunked E5 Raw Top-10 Chunks Note*: Without wave-doc MaxP deduplication, raw Top-10 chunk retrieval (`15,687` chunks) yields **Topic R@1 = 67.07%**, **Topic R@3 = 72.17%**, **Topic R@10 = 78.55%**, **`58.49%` wasted Top-3 slots**, **`81.22%` wasted Top-10 slots**, and only **`1.88 / 10` unique topics** in Top-10.

## 3. Gold Answer Containment & Long-Passage Breakdown (4,485 QAs)

| System | Overall Ans@1 | Overall Ans@3 | Overall Ans@10 | Standard (`<=2,000c`, `2,711` QAs) R@1 / R@10 | **Long (`>2,000c`, `1,774` QAs) R@1 / R@10** | Top-1 Sent Span | Top-1 Sent >=0.5 | Top-1 Sent Recall / F1 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. E5-Large Whole-Passage RAG (5,360 Raw Wave Docs)** | 58.51% | 62.27% | 69.30% | 66.55% / 77.47% | **41.69% / 53.35%** | 43.39% | 48.92% | 51.47% / 24.57% |
| **2. E5-Large Sub-Chunked (<=1000c, Wave-Doc MaxP, 15,687 chunks)** | 66.11% | 71.62% | 79.09% | 67.09% / 78.16% | **67.05% / 79.68%** | 53.11% | 59.62% | 61.48% / 28.78% |
| **3. LLM Wiki Consolidated Vault (548 Pages)** | 80.94% | 91.86% | 96.90% | 78.36% / 96.34% | **74.28% / 95.45%** | 61.72% | 66.67% | 67.69% / 32.40% |
| **4. Hybrid LLM Wiki + E5 Fusion (548 Consolidated Pages)** | 83.03% | 93.47% | 97.75% | 78.85% / 96.64% | **76.64% / 96.79%** | 62.74% | 67.49% | 68.74% / 32.82% |

## 4. Build, Ingest & Query Latency (5,360 Passages, 4,485 Queries)

| System | Build / Ingest Time | 4,485-Query Time | Per-Query Latency |
| :--- | :---: | :---: | :---: |
| **1. E5-Large Whole-Passage RAG (5,360 Raw Wave Docs)** | `462.77s` | `5.30s` | `1.18 ms/query` |
| **2. E5-Large Sub-Chunked (<=1000c, Wave-Doc MaxP, 15,687 chunks)** | `962.92s` | `9.52s` | `2.12 ms/query` |
| **3. LLM Wiki Consolidated Vault (548 Pages)** | `20.36s` | `10.42s` | `2.32 ms/query` |
| **4. Hybrid LLM Wiki + E5 Fusion (548 Consolidated Pages)** | `143.21s` | `16.45s` | `3.67 ms/query` |

## 5. Key Honest Takeaways
1. **With True Full-Passage 10x Redundancy, E5 R@1 Stays Near 1x While R@3..R@10 Collapse Under Duplicate Crowding**: E5 Whole-Passage Topic R@1 is **52.91%** (vs `50.06%` at 1x), while **Topic R@3 drops from `65.69%` to `56.79%`** and **Topic R@10 drops from `78.08%` to `64.24%`** because `79.86%` of Top-10 slots are crowded by redundant copies (`2.01 / 10` unique topics). Likewise, E5 Sub-Chunked R@1 stays at **67.07%** (vs `63.52%` at 1x), while its **Topic R@3 drops from `79.18%` to `72.24%`** and **Topic R@10 drops from `88.94%` to `79.00%`** (`1.94 / 10` unique topics).
2. **100% Blind LLM Wiki Consolidation Collapses `5,360` Passages into `548` Pages**: Without any Wave-1 bypass or ground-truth tags, `HybridSimilarityEngine` created `532` pages in Wave 1 (merging `4` near-identical pairs in raw TeleQuAD, including 2 word-for-word duplicate web scrapes) and consolidated **`4,808/4,824` (99.67%)** of Waves 2–10 into canonical pages (`548` total pages including `16` blind-title edge cases).
3. **Minimal Duplicate Crowding Preserves High Recall at Top-K**: Because the consolidated wiki vault has only `4.16%` duplicate slot waste (`9.56 / 10` unique topics in Top-10 vs `2.01 / 10` for E5), LLM Wiki achieves **76.12% Topic R@1** (`75.94%` strict 1-to-1) and **95.85% Topic R@10** (`95.63%` strict 1-to-1), while Hybrid LLM Wiki + E5 Fusion reaches **77.64% Topic R@1** (`77.48%` strict) and **96.72% Topic R@10** (`96.50%` strict).
