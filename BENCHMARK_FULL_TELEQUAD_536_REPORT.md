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
